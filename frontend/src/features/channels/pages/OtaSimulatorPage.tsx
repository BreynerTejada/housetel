import { ChevronLeft, ChevronRight, FlaskConical, Lock, Network, Send, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { DatePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { useLocalStorageState } from '@/lib/hooks'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useRuntimeConfig } from '@/lib/runtime'
import {
  pullConnection,
  retryQueue,
  useChannelOptions,
  useChannelsMutation,
  useConnections,
  useSimInventory,
  type Connection,
  type OtaBooking,
} from '../api'
import { ChannelMark } from '../components/ChannelMark'
import { OtaBookingDialog, type OtaBookingPreset } from '../components/OtaBookingDialog'
import { OtaBookingsPanel } from '../components/OtaBookingsPanel'
import { OtaInventoryGrid, type OtaCellPick } from '../components/OtaInventoryGrid'
import { addDaysISO } from '../lib/channels'
import { otaDomain } from '../lib/labels'
import '../components/ota.css'

const SPANS = [14, 30] as const
const LIVE_MS = 5_000

interface DialogState {
  open: boolean
  key: number
  booking: OtaBooking | null
  preset: OtaBookingPreset | null
}

/**
 * `/app/simulators/ota`: act as BookSim, AirSim or the simulated Channex. "What the OTA sees" is the ARI Housetel
 * pushed (refreshed live, changed cells glow); "OTA bookings" creates, changes and cancels bookings that reach
 * the PMS by the same path as a real channel.
 */
export default function OtaSimulatorPage() {
  const { t } = useTranslation('channels')
  const { property } = useActiveProperty()
  const canManage = useCan('distribution.manage')
  const runtime = useRuntimeConfig()
  if (!property || !runtime.loaded) return <LoadingState variant="rows" rows={6} />
  if (!runtime.simulations_enabled) {
    // A development/demo tool: where simulations are off (production) the API answers 404 and nothing is shown.
    return (
      <div className="grid gap-2">
        <PageHeader title={t('sim.title')} description={t('sim.description')} />
        <EmptyState icon={ShieldAlert} title={t('sim.unavailableTitle')} description={t('sim.unavailableHint')} />
      </div>
    )
  }
  if (!canManage) {
    return (
      <div className="grid gap-2">
        <PageHeader title={t('sim.title')} description={t('sim.description')} />
        <EmptyState icon={ShieldAlert} title={t('sim.forbiddenTitle')} description={t('sim.forbiddenHint')} />
      </div>
    )
  }
  return <Simulator key={property.id} today={property.business_date} propertySlug={property.slug} />
}

function Simulator({ today, propertySlug }: { today: string; propertySlug: string }) {
  const { t } = useTranslation('channels')
  const [params, setParams] = useSearchParams()
  const connectionsQuery = useConnections({ refetchInterval: LIVE_MS })
  const simulated = (connectionsQuery.data ?? []).filter((item) => item.simulated)
  const requested = params.get('connection')
  const connection = simulated.find((item) => item.id === requested) ?? simulated[0]

  function choose(id: string) {
    const next = new URLSearchParams(params)
    next.set('connection', id)
    setParams(next, { replace: true })
  }

  return (
    <div className="grid gap-2">
      <PageHeader
        title={t('sim.title')}
        description={t('sim.description')}
        actions={
          <Button asChild>
            <Link to="/app/channels">
              <Network aria-hidden /> {t('sim.backToChannels')}
            </Link>
          </Button>
        }
      />

      {connectionsQuery.isPending ? (
        <LoadingState variant="rows" rows={6} />
      ) : connectionsQuery.isError && !connectionsQuery.data ? (
        <ErrorState error={connectionsQuery.error} onRetry={() => void connectionsQuery.refetch()} />
      ) : !connection ? (
        <EmptyState
          icon={FlaskConical}
          title={t('sim.emptyTitle')}
          description={t('sim.emptyHint')}
          action={
            <Button asChild variant="primary">
              <Link to="/app/channels">{t('sim.connectOne')}</Link>
            </Button>
          }
        />
      ) : (
        <>
          {simulated.length > 1 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label={t('sim.pickOta')}>
              {simulated.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={item.id === connection.id}
                  onClick={() => choose(item.id)}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                    item.id === connection.id ? 'border-accent bg-accent-soft text-accent-ink' : 'border-border bg-surface text-fg hover:border-border-strong',
                  )}
                >
                  <ChannelMark channel={item.channel_code} size="sm" />
                  {item.name}
                  {item.status !== 'active' && <Badge tone={item.status === 'error' ? 'danger' : 'stone'}>{t(`status.${item.status}`)}</Badge>}
                </button>
              ))}
            </div>
          )}
          <OtaWindow key={connection.id} connection={connection} today={today} propertySlug={propertySlug} />
        </>
      )}
    </div>
  )
}

function OtaWindow({ connection, today, propertySlug }: { connection: Connection; today: string; propertySlug: string }) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const [tab, setTab] = useState<'inventory' | 'bookings'>('inventory')
  const [start, setStart] = useState(today)
  const [storedSpan, setSpan] = useLocalStorageState<number>('housetel.channels.simSpan', 14)
  const span = (SPANS as readonly number[]).includes(storedSpan) ? storedSpan : 14
  const end = addDaysISO(start, span)
  const inventoryQuery = useSimInventory(connection.id, start, end, { refetchInterval: LIVE_MS })
  const optionsQuery = useChannelOptions()
  const [dialog, setDialog] = useState<DialogState>({ open: false, key: 0, booking: null, preset: null })
  const inventory = inventoryQuery.data
  const pending = connection.stats.pending_updates + connection.stats.failed_updates
  const paused = connection.status === 'paused'

  const roomKinds = useMemo(() => {
    const kinds: Record<string, 'private' | 'dorm'> = {}
    for (const roomType of optionsQuery.data?.room_types ?? []) kinds[roomType.id] = roomType.kind
    return kinds
  }, [optionsQuery.data])

  const push = useChannelsMutation(() => retryQueue(connection.id), {
    onSuccess: (result) => toast.success(result.sent ? t('queue.sent', { count: result.sent }) : t('queue.nothingToSend')),
  })
  const download = useChannelsMutation(() => pullConnection(connection.id), {
    onSuccess: (summary) => toast.success(t('card.pulled', { created: summary.created ?? 0, modified: summary.modified ?? 0, cancelled: summary.cancelled ?? 0 })),
  })

  function openDialog(booking: OtaBooking | null, preset: OtaBookingPreset | null = null) {
    setDialog((current) => ({ open: true, key: current.key + 1, booking, preset }))
  }

  function pick({ room, rate, date, cell }: OtaCellPick) {
    const nights = Math.max(cell.min_los ?? 1, 1)
    openDialog(null, { room: room.external_room_id, rate: rate.external_rate_id, checkin: date, checkout: addDaysISO(date, nights) })
  }

  function done(booking: OtaBooking, created: boolean) {
    setDialog((current) => ({ ...current, open: false }))
    setTab('bookings')
    const reservation = booking.reservation
    if (booking.pms_status === 'failed') {
      toast.error(t('otaBooking.importFailed', { id: booking.external_id, message: booking.pms_message }))
    } else if (reservation) {
      toast.success(created ? t('otaBooking.created', { id: booking.external_id, code: reservation.code }) : t('otaBooking.modified', { id: booking.external_id, code: reservation.code }), {
        action: { label: t('otaBooking.openReservation'), onClick: () => navigate(`/app/reservations/${reservation.id}`) },
      })
    } else {
      toast.success(t('otaBooking.waitingPull', { id: booking.external_id }), {
        action: { label: t('otaBookings.pullNow'), onClick: () => download.mutate(undefined, { onError: (error) => toast.error(errorMessage(error, t)) }) },
      })
    }
  }

  return (
    <section className="ota-window overflow-hidden rounded-xl border border-border bg-surface shadow-sm" data-channel={connection.channel_code} aria-label={t('sim.windowLabel', { ota: connection.name })}>
      {/* The OTA's own screen: a pseudo address bar says whose side of the connection this is. */}
      <div className="flex items-center gap-3 border-b border-border bg-surface-2/70 px-3 py-2 sm:px-4">
        <span aria-hidden className="hidden gap-1.5 sm:flex">
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
        </span>
        <span className="flex min-w-0 flex-1 items-center gap-2 rounded-md bg-surface px-2.5 py-1 text-xs text-muted">
          <Lock aria-hidden className="size-3 shrink-0" />
          <span className="num truncate">
            {otaDomain(connection.channel_code)}/{propertySlug}
          </span>
        </span>
        <Badge tone="neutral" className="hidden sm:inline-flex">
          {connection.delivery === 'pull' ? t('sim.deliveryPull') : t('sim.deliveryPush')}
        </Badge>
      </div>

      <header className="flex flex-wrap items-center gap-3 px-4 pt-4 sm:px-5">
        <ChannelMark channel={connection.channel_code} size="lg" />
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] leading-6 font-bold tracking-[-0.015em] text-fg">{t('sim.extranet', { ota: connection.name })}</h2>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
            {inventory?.last_update ? (
              <>
                <span className="ota-live-dot" aria-hidden />
                <span>{t('sim.lastAri', { when: formatRelative(inventory.last_update, lang) })}</span>
              </>
            ) : (
              <span>{t('sim.noAri')}</span>
            )}
            <span aria-hidden>·</span>
            <span>{t('sim.live')}</span>
          </p>
        </div>
        {pending > 0 && (
          <Button size="sm" onClick={() => push.mutate(undefined, { onError: (error) => toast.error(errorMessage(error, t)) })} loading={push.isPending} disabled={paused}>
            <Send aria-hidden /> {t('sim.pushPending', { count: pending })}
          </Button>
        )}
      </header>

      {paused && <p className="mx-4 mt-3 rounded-lg bg-stone-soft px-3 py-2 text-[13px] text-stone-ink sm:mx-5">{t('sim.paused')}</p>}

      <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)} className="px-4 pb-5 sm:px-5">
        <TabsList aria-label={t('sim.sections')}>
          <TabsTrigger value="inventory">{t('sim.tabs.inventory')}</TabsTrigger>
          <TabsTrigger value="bookings">
            {t('sim.tabs.bookings')}
            {connection.stats.reservations > 0 && <Badge tone="neutral">{connection.stats.reservations}</Badge>}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="inventory" className="grid gap-3">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
            <div className="grid gap-1.5">
              <Label htmlFor="ota-start">{t('sim.from')}</Label>
              <div className="flex items-center gap-1">
                <Button size="icon" aria-label={t('sim.previousWeek')} onClick={() => setStart(addDaysISO(start, -7))}>
                  <ChevronLeft aria-hidden />
                </Button>
                <DatePicker id="ota-start" value={start} onChange={(value) => value && setStart(value)} className="w-44" />
                <Button size="icon" aria-label={t('sim.nextWeek')} onClick={() => setStart(addDaysISO(start, 7))}>
                  <ChevronRight aria-hidden />
                </Button>
                <Button variant="ghost" onClick={() => setStart(today)} disabled={start === today}>
                  {t('sim.today')}
                </Button>
              </div>
            </div>
            <ToggleGroup type="single" value={String(span)} onValueChange={(value) => value && setSpan(Number(value))} aria-label={t('sim.span')}>
              {SPANS.map((value) => (
                <ToggleGroupItem key={value} value={String(value)}>
                  {t('sim.spanNights', { count: value })}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          {inventoryQuery.isPending ? (
            <LoadingState variant="rows" rows={6} />
          ) : inventoryQuery.isError && !inventoryQuery.data ? (
            <ErrorState error={inventoryQuery.error} onRetry={() => void inventoryQuery.refetch()} />
          ) : !inventory || inventory.rooms.length === 0 ? (
            <EmptyState icon={FlaskConical} title={t('sim.noRooms')} description={t('sim.noRoomsHint')} />
          ) : (
            <OtaInventoryGrid inventory={inventory} today={today} onPick={paused ? undefined : pick} />
          )}
          <Legend />
        </TabsContent>

        <TabsContent value="bookings">
          <OtaBookingsPanel connection={connection} today={today} onCreate={() => openDialog(null)} onModify={(booking) => openDialog(booking)} />
        </TabsContent>
      </Tabs>

      <OtaBookingDialog
        key={dialog.key}
        open={dialog.open}
        onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
        connection={connection}
        today={today}
        currency={inventory?.currency ?? optionsQuery.data?.currency ?? 'COP'}
        booking={dialog.booking}
        preset={dialog.preset}
        roomKinds={roomKinds}
        onDone={done}
      />
    </section>
  )
}

function Legend() {
  const { t } = useTranslation('channels')
  const items = [
    { key: 'open', swatch: 'bg-surface border border-border', label: t('sim.legend.open') },
    { key: 'soldout', swatch: 'bg-danger-soft', label: t('sim.legend.soldOut') },
    { key: 'closed', swatch: 'hatch bg-surface border border-border', label: t('sim.legend.closed') },
    { key: 'missing', swatch: 'hatch bg-surface-2 border border-border', label: t('sim.legend.missing') },
  ]
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted" aria-label={t('sim.legend.title')}>
      {items.map((item) => (
        <li key={item.key} className="inline-flex items-center gap-1.5">
          <span aria-hidden className={cn('size-3 rounded-sm', item.swatch)} />
          {item.label}
        </li>
      ))}
      <li className="inline-flex items-center gap-1.5">
        <span className="num font-semibold text-info-ink">2n</span> {t('sim.legend.minLos')}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-3 rounded-sm ring-2 ring-accent ring-inset" /> {t('sim.legend.changed')}
      </li>
      <li>{t('sim.legend.click')}</li>
    </ul>
  )
}
