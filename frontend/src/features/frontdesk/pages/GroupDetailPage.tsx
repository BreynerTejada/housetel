import { ChevronRight, Download, MoreHorizontal, Pencil, Plus, SearchX, Trash2, UserPlus, UsersRound } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { saveBlob } from '@/features/finance/download'
import { useActiveProperty } from '@/lib/auth'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { deleteGroup, exportRooming, useGroup, useRefreshFrontDesk, type GroupBlock, type GroupDetail } from '../api'
import { AddReservationDialog } from '../components/groups/AddReservationDialog'
import { BlockCard } from '../components/groups/BlockCard'
import { BlockFormDialog } from '../components/groups/BlockFormDialog'
import { GroupFormDialog } from '../components/groups/GroupFormDialog'
import { GroupReservations } from '../components/groups/GroupReservations'
import { RoomingList } from '../components/groups/RoomingList'
import { GROUP_STATE_TONE, groupNights, pickupTone, unnamedRooms } from '../lib/groups'

type OpenDialog = { kind: 'edit' } | { kind: 'block'; block?: GroupBlock } | { kind: 'addExisting' } | { kind: 'delete' }

/**
 * `/app/groups/:id` (pilot P3): one group — a wedding, a congress, a delegation. Its allotments night by night
 * (what is held, what the group took, when the rest goes back on sale), the rooming list with the name of whoever
 * sleeps in each room, and its reservations, with ways to add more.
 */
export default function GroupDetailPage() {
  const { id } = useParams()
  const { t } = useTranslation('frontdesk')
  const group = useGroup(id)
  if (group.isError) {
    if (isApiError(group.error) && group.error.status === 404) {
      return (
        <EmptyState
          icon={SearchX}
          title={t('groups.notFound')}
          description={t('groups.notFoundHint')}
          action={
            <Button asChild>
              <Link to="/app/groups">{t('groups.backToList')}</Link>
            </Button>
          }
        />
      )
    }
    return <ErrorState error={group.error} onRetry={() => group.refetch()} />
  }
  if (!group.data) return <LoadingState />
  return <Detail group={group.data} />
}

function Detail({ group }: { group: GroupDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const refresh = useRefreshFrontDesk()
  const { property } = useActiveProperty()
  const bd = group.business_date || property?.business_date || ''
  const canManage = useCan('bookings.manage')
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const [exporting, setExporting] = useState(false)
  const close = () => setDialog(null)
  const figures = group.figures
  const nights = groupNights(figures)
  const openBlocks = group.blocks.filter((block) => !block.released_at)

  // A new reservation of the group starts on its dates (from today on, when the group already arrived).
  const wizard = new URLSearchParams({ group: group.id })
  if (figures?.start && figures.end && figures.end > bd) {
    wizard.set('checkin', figures.start < bd ? bd : figures.start)
    wizard.set('checkout', figures.end)
  }

  async function exportCsv() {
    setExporting(true)
    try {
      const blob = await exportRooming(group.id, lang)
      const slug = group.name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'grupo'
      saveBlob(blob, `rooming-${slug}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setExporting(false)
    }
  }

  async function remove() {
    await deleteGroup(group.id)
    await refresh()
    toast.success(t('groups.deleted', { name: group.name }))
    navigate('/app/groups', { replace: true })
  }

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6">
      <nav aria-label={t('detail.breadcrumb')} className="flex min-w-0 items-center gap-1 text-[13px] text-muted">
        <Link to="/app/groups" className="rounded-sm hover:text-fg hover:underline">
          {t('nav.groups')}
        </Link>
        <ChevronRight aria-hidden className="size-3.5 shrink-0 text-subtle" />
        <span className="truncate">{group.name}</span>
      </nav>

      <section aria-label={t('groups.region', { name: group.name })} className="rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
        <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="eyebrow">{t('groups.eyebrow')}</span>
              {figures && figures.state !== 'empty' && <Badge tone={GROUP_STATE_TONE[figures.state]}>{t(`groups.state.${figures.state}`)}</Badge>}
            </div>
            <h1 className="mt-1.5 text-[26px] leading-8 tracking-[-0.025em] break-words text-fg">{group.name}</h1>
            <p className="num mt-1 text-[13px] text-muted">
              {figures?.start && figures.end ? (
                <>
                  <span className="font-semibold text-fg">{formatDateRange(figures.start, figures.end, lang)}</span> · {t('date.nights', { count: nights })}
                </>
              ) : (
                t('groups.noDates')
              )}
            </p>
            <p className="mt-2 text-[13px] text-fg">
              {group.contact_guest ? (
                <>
                  <span className="text-muted">{t('groups.contactLabel')} </span>
                  <span className="font-semibold">{group.contact_guest.full_name}</span>
                  {[group.contact_guest.email, group.contact_guest.phone].filter(Boolean).length > 0 && (
                    <span className="text-muted"> · {[group.contact_guest.email, group.contact_guest.phone].filter(Boolean).join(' · ')}</span>
                  )}
                </>
              ) : (
                <span className="text-muted">{t('groups.noContact')}</span>
              )}
            </p>
            {group.notes && <p className="mt-2 max-w-2xl text-[13px] whitespace-pre-line text-muted">{group.notes}</p>}
          </div>
          {canManage && (
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Button asChild variant="primary">
                <Link to={`/app/reservations/new?${wizard.toString()}`}>
                  <UserPlus aria-hidden />
                  {t('groups.newReservation')}
                </Link>
              </Button>
              <Button variant="secondary" onClick={() => setDialog({ kind: 'edit' })}>
                <Pencil aria-hidden />
                {t('common:actions.edit')}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label={t('detail.moreActions')}>
                    <MoreHorizontal aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => void exportCsv()} disabled={exporting || group.rooming.length === 0}>
                    <Download aria-hidden />
                    {t('groups.rooming.export')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem destructive onSelect={() => setDialog({ kind: 'delete' })}>
                    <Trash2 aria-hidden />
                    {t('groups.delete')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
        </div>
      </section>

      <GroupFigures group={group} />

      <Section
        title={t('groups.sections.blocks')}
        hint={t('groups.sections.blocksHint')}
        count={group.blocks.length}
        actions={
          canManage && (
            <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: 'block' })}>
              <Plus aria-hidden />
              {t('groups.blocks.new')}
            </Button>
          )
        }
      >
        {group.blocks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border-strong px-4 py-6 text-center text-[13px] text-muted">{t('groups.blocks.empty')}</p>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {[...openBlocks, ...group.blocks.filter((block) => block.released_at)].map((block) => (
              <BlockCard key={block.id} block={block} groupId={group.id} bd={bd} canManage={canManage} onEdit={(item) => setDialog({ kind: 'block', block: item })} />
            ))}
          </div>
        )}
      </Section>

      <Section
        title={t('groups.sections.rooming')}
        hint={t('groups.sections.roomingHint')}
        count={group.rooming.length}
        badge={
          group.rooming.length > 0 &&
          (unnamedRooms(group.rooming) > 0 ? (
            <Badge tone="warning">{t('groups.rooming.unnamed', { count: unnamedRooms(group.rooming) })}</Badge>
          ) : (
            <Badge tone="success">{t('groups.rooming.complete')}</Badge>
          ))
        }
        actions={
          group.rooming.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => void exportCsv()} loading={exporting}>
              <Download aria-hidden />
              {t('groups.rooming.exportShort')}
            </Button>
          )
        }
      >
        <RoomingList group={group} canManage={canManage} />
      </Section>

      <Section
        title={t('groups.sections.reservations')}
        count={group.reservations.length}
        actions={
          canManage && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: 'addExisting' })}>
                <UsersRound aria-hidden />
                {t('groups.addExisting.action')}
              </Button>
              <Button asChild size="sm" variant="secondary">
                <Link to={`/app/reservations/new?${wizard.toString()}`}>
                  <Plus aria-hidden />
                  {t('groups.newReservationShort')}
                </Link>
              </Button>
            </>
          )
        }
      >
        <GroupReservations group={group} canManage={canManage} />
      </Section>

      {dialog?.kind === 'edit' && <GroupFormDialog open onOpenChange={(open) => !open && close()} group={group} />}
      {dialog?.kind === 'block' && (
        <BlockFormDialog
          open
          onOpenChange={(open) => !open && close()}
          groupId={group.id}
          block={dialog.block}
          bd={bd}
          defaultRange={figures?.start && figures.end ? { from: figures.start, to: figures.end } : undefined}
        />
      )}
      {dialog?.kind === 'addExisting' && <AddReservationDialog open onOpenChange={(open) => !open && close()} groupId={group.id} groupName={group.name} />}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && close()}
          title={t('groups.deleteTitle', { name: group.name })}
          description={t('groups.deleteHint', { count: openBlocks.length })}
          confirmLabel={t('groups.delete')}
          onConfirm={remove}
        />
      )}
    </div>
  )
}

function Section({
  title,
  hint,
  count,
  badge,
  actions,
  children,
}: {
  title: string
  hint?: string
  count: number
  badge?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="grid gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-2 text-[15px] font-bold text-fg">
            {title}
            <span className="num text-[13px] font-semibold text-muted">{count}</span>
            {badge}
          </h2>
          {hint && <p className="text-[13px] text-muted">{hint}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-1.5">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

/** The group in four figures: rooms, allotment pickup, how complete the rooming list is, what it owes. */
function GroupFigures({ group }: { group: GroupDetail }) {
  const { t } = useTranslation('frontdesk')
  const figures = group.figures
  const rooms = group.rooming.length
  const named = rooms - unnamedRooms(group.rooming)
  const balance = Number(figures?.balance ?? 0)
  const pct = figures?.pickup_pct
  return (
    <section aria-label={t('groups.figures')} className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border shadow-xs lg:grid-cols-4">
      <Figure label={t('groups.figure.rooms')} value={String(figures?.rooms ?? 0)} sub={t('groups.reservations', { count: figures?.reservations ?? 0 })} />
      <Figure
        label={t('groups.figure.pickup')}
        value={pct === null || pct === undefined ? '—' : `${Math.round(pct)} %`}
        meter={figures && figures.room_nights > 0 ? { value: figures.picked_room_nights, max: figures.room_nights, tone: pickupTone(pct) } : undefined}
        sub={figures && figures.blocks > 0 ? t('groups.pickupRooms', { rooms: figures.picked_rooms, units: figures.blocked_units }) : t('groups.noBlocks')}
      />
      <Figure
        label={t('groups.figure.names')}
        value={rooms > 0 ? `${named}/${rooms}` : '—'}
        meter={rooms > 0 ? { value: named, max: rooms, tone: named === rooms ? 'success' : 'warning' } : undefined}
        sub={rooms === 0 ? t('groups.rooming.noRooms') : named === rooms ? t('groups.rooming.complete') : t('groups.rooming.unnamed', { count: rooms - named })}
      />
      <Figure
        label={t('groups.figure.balance')}
        value={formatMoney(figures?.balance ?? '0', group.currency)}
        valueClass={balance > 0 ? 'text-warning-ink' : undefined}
        sub={balance > 0 ? t('groups.figure.toCollect') : t('groups.figure.settled')}
      />
    </section>
  )
}

const METER_FILL: Record<string, string> = { success: 'bg-success', info: 'bg-info', warning: 'bg-warning', neutral: 'bg-stone' }

function Figure({
  label,
  value,
  sub,
  meter,
  valueClass,
}: {
  label: string
  value: string
  sub: string
  meter?: { value: number; max: number; tone: string }
  valueClass?: string
}) {
  const ratio = meter && meter.max > 0 ? Math.min(1, meter.value / meter.max) : 0
  return (
    <div className="grid content-start gap-1.5 bg-surface px-4 py-3.5">
      <p className="text-xs font-semibold text-muted">{label}</p>
      <p className={cn('num text-[22px] leading-7 font-bold tracking-[-0.02em] text-fg', valueClass)}>{value}</p>
      {meter && (
        <span
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={meter.max}
          aria-valuenow={meter.value}
          className="block h-1 overflow-hidden rounded-full bg-surface-3"
        >
          <span className={cn('block h-full rounded-full', METER_FILL[meter.tone] ?? 'bg-accent')} style={{ width: `${ratio * 100}%` }} />
        </span>
      )}
      <p className="truncate text-xs text-muted">{sub}</p>
    </div>
  )
}
