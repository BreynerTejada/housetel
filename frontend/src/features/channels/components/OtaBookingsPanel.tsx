import { ChevronLeft, ChevronRight, CloudDownload, ExternalLink, Pencil, Plus, Send, ShoppingBag, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, formatMoney, formatRelative, nightsBetween, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  cancelSimBooking,
  deliverSimBooking,
  pullConnection,
  useChannelsMutation,
  useSimBookings,
  type Connection,
  type OtaBooking,
} from '../api'
import { PMS_STATUS_TONE, SIM_STATUS_TONE } from '../lib/labels'

const PAGE_SIZE = 20

/**
 * The bookings made in the simulated OTA, each with the PMS reservation it became. BookSim and AirSim deliver
 * every revision at once; the simulated Channex keeps them until the PMS pulls its feed.
 */
export function OtaBookingsPanel({
  connection,
  today,
  onCreate,
  onModify,
}: {
  connection: Connection
  /** Business date: bookings already over cannot be changed in the OTA. */
  today: string
  onCreate: () => void
  onModify: (booking: OtaBooking) => void
}) {
  const { t } = useTranslation('channels')
  const [page, setPage] = useState(1)
  const [cancelling, setCancelling] = useState<OtaBooking | null>(null)
  const query = useSimBookings(connection.id, page, { refetchInterval: 10_000 })
  const data = query.data
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1
  const pull = connection.delivery === 'pull'
  const waiting = data?.results.filter((booking) => booking.pms_status === 'pending').length ?? 0

  const cancel = useChannelsMutation((booking: OtaBooking) => cancelSimBooking(connection.id, booking.external_id), {
    onSuccess: (booking) =>
      booking.pms_status === 'failed'
        ? toast.error(t('otaBookings.cancelFailed', { id: booking.external_id, message: booking.pms_message }))
        : toast.success(pull ? t('otaBookings.cancelledPending', { id: booking.external_id }) : t('otaBookings.cancelled', { id: booking.external_id })),
  })
  const deliver = useChannelsMutation((booking: OtaBooking) => deliverSimBooking(connection.id, booking.external_id), {
    onSuccess: (booking) =>
      booking.pms_status === 'failed'
        ? toast.error(t('otaBookings.deliverFailed', { message: booking.pms_message }))
        : toast.success(t('otaBookings.delivered', { id: booking.external_id })),
  })
  const download = useChannelsMutation(() => pullConnection(connection.id), {
    onSuccess: (summary) =>
      summary.failed
        ? toast.error(t('card.pulledWithErrors', { count: summary.failed }))
        : toast.success(
            (summary.created ?? 0) + (summary.modified ?? 0) + (summary.cancelled ?? 0)
              ? t('card.pulled', { created: summary.created ?? 0, modified: summary.modified ?? 0, cancelled: summary.cancelled ?? 0 })
              : t('card.pulledNothing'),
          ),
  })
  const onError = (error: unknown) => toast.error(errorMessage(error, t))

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto text-[13px] text-muted">{pull ? t('otaBookings.pullHint') : t('otaBookings.pushHint', { ota: connection.name })}</p>
        {pull && (
          <Button size="sm" onClick={() => download.mutate(undefined, { onError })} loading={download.isPending} disabled={connection.status === 'paused'}>
            <CloudDownload aria-hidden /> {t('otaBookings.pullNow')}
            {waiting > 0 && <Badge tone="warning">{waiting}</Badge>}
          </Button>
        )}
        <Button size="sm" variant="primary" onClick={onCreate}>
          <Plus aria-hidden /> {t('otaBookings.new')}
        </Button>
      </div>

      <div className={cn('overflow-hidden rounded-lg border border-border bg-surface shadow-xs', query.isFetching && data && 'opacity-90')}>
        {query.isPending ? (
          <LoadingState variant="rows" rows={5} />
        ) : query.isError && !query.data ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            icon={ShoppingBag}
            title={t('otaBookings.empty', { ota: connection.name })}
            description={t('otaBookings.emptyHint')}
            action={
              <Button variant="primary" onClick={onCreate}>
                <Plus aria-hidden /> {t('otaBookings.new')}
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-border">
            {data.results.map((booking) => (
              <BookingRow
                key={booking.id}
                booking={booking}
                pull={pull}
                today={today}
                busy={(cancel.isPending && cancel.variables?.id === booking.id) || (deliver.isPending && deliver.variables?.id === booking.id)}
                onModify={() => onModify(booking)}
                onCancel={() => setCancelling(booking)}
                onDeliver={() => deliver.mutate(booking, { onError })}
              />
            ))}
          </ul>
        )}
        {data && data.count > PAGE_SIZE && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2 text-[13px] text-muted">
            <span className="num">{t('otaBookings.total', { count: data.count })}</span>
            <div className="flex items-center gap-2">
              <span className="num">{t('log.page', { page, pages })}</span>
              <Button size="icon-sm" aria-label={t('log.previous')} disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button size="icon-sm" aria-label={t('log.next')} disabled={!data.next} onClick={() => setPage(page + 1)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={cancelling !== null}
        onOpenChange={(open) => !open && setCancelling(null)}
        title={t('otaBookings.cancelTitle', { id: cancelling?.external_id ?? '', ota: connection.name })}
        description={pull ? t('otaBookings.cancelPullDescription') : t('otaBookings.cancelDescription')}
        confirmLabel={t('otaBookings.cancel')}
        onConfirm={() => (cancelling ? cancel.mutateAsync(cancelling) : undefined)}
      />
    </div>
  )
}

function BookingRow({
  booking,
  pull,
  today,
  busy,
  onModify,
  onCancel,
  onDeliver,
}: {
  booking: OtaBooking
  pull: boolean
  today: string
  busy: boolean
  onModify: () => void
  onCancel: () => void
  onDeliver: () => void
}) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const room = booking.payload.rooms[0]
  const guest = booking.payload.guest ?? {}
  const name = [guest.first_name, guest.last_name].filter(Boolean).join(' ') || t('otaBookings.anonymous')
  const nights = room ? nightsBetween(room.checkin, room.checkout) : 0
  const cancelled = booking.status === 'cancelled'
  const over = room ? room.checkout <= today : false
  const canRedeliver = !pull && booking.pms_status !== 'imported'

  return (
    <li className={cn('grid gap-3 px-3 py-3 sm:px-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_15.5rem] lg:items-center', cancelled && 'bg-surface-2/40')}>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <span className="num text-[13px] font-bold text-fg">{booking.external_id}</span>
          <Badge tone={SIM_STATUS_TONE[booking.status]}>{t(`otaBookings.status.${booking.status}`)}</Badge>
          {booking.revision > 1 && <span className="text-2xs font-semibold text-muted">{t('otaBookings.revision', { revision: booking.revision })}</span>}
          {booking.payload.forced && <Badge tone="danger">{t('otaBookings.forced')}</Badge>}
        </p>
        <p className="mt-0.5 truncate text-[13px] text-fg">
          {name}
          {guest.country && <span className="text-muted"> · {guest.country}</span>}
        </p>
        {room && (
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
            <span className="num">
              {room.external_room_id} · {room.external_rate_id}
            </span>
            <span aria-hidden>·</span>
            <span className="num">{formatDateRange(room.checkin, room.checkout, lang)}</span>
            <span>({t('queue.nights', { count: nights })})</span>
            <span aria-hidden>·</span>
            <span>{t('otaBookings.guests', { adults: room.adults, children: room.children })}</span>
          </p>
        )}
      </div>

      <div className="grid gap-1 text-[13px]">
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">{t('otaBookings.pms')}</span>
          {booking.reservation ? (
            <>
              <Link to={`/app/reservations/${booking.reservation.id}`} className="num inline-flex items-center gap-1 font-bold text-accent-ink hover:underline">
                {booking.reservation.code} <ExternalLink aria-hidden className="size-3" />
              </Link>
              <StatusBadge kind="reservation" status={booking.reservation.status} />
            </>
          ) : (
            <Badge tone={PMS_STATUS_TONE[booking.pms_status]}>{t(`otaBookings.pmsStatus.${booking.pms_status}`, { context: pull ? 'pull' : undefined })}</Badge>
          )}
          {booking.reservation && booking.pms_status !== 'imported' && (
            <Badge tone={PMS_STATUS_TONE[booking.pms_status]}>{t(`otaBookings.pmsStatus.${booking.pms_status}`, { context: pull ? 'pull' : undefined })}</Badge>
          )}
        </p>
        {booking.pms_message && booking.pms_status === 'failed' && <p className="text-xs text-danger-ink">{booking.pms_message}</p>}
        <p className="text-xs text-muted">
          {booking.payload.total ? <span className="num font-semibold text-fg">{formatMoney(booking.payload.total, booking.payload.currency)}</span> : t('otaBookings.noTotal')}
          <span aria-hidden> · </span>
          <time dateTime={booking.updated_at} title={formatDate(booking.updated_at, 'd MMM yyyy, HH:mm', lang)}>
            {formatRelative(booking.updated_at, lang)}
          </time>
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
        {canRedeliver && (
          <Button size="sm" onClick={onDeliver} loading={busy}>
            <Send aria-hidden /> {t('otaBookings.deliver')}
          </Button>
        )}
        {over && !cancelled && <span className="text-xs text-muted">{t('otaBookings.over')}</span>}
        {!cancelled && !over && (
          <>
            <Button size="sm" variant="ghost" onClick={onModify} disabled={busy}>
              <Pencil aria-hidden /> {t('otaBookings.modify')}
            </Button>
            <Button size="sm" variant="ghost" className="text-danger-ink" onClick={onCancel} disabled={busy}>
              <X aria-hidden /> {t('otaBookings.cancel')}
            </Button>
          </>
        )}
      </div>
    </li>
  )
}
