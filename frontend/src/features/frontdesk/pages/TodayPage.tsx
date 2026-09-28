import { addDays } from 'date-fns'
import { DoorOpen, MoonStar, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate } from 'react-router'
import { useNav, useWidgets } from '@/app/extensions'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useActiveMembership, useActiveProperty, useMe } from '@/lib/auth'
import { formatDate, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { usePermissionChecker } from '@/lib/permissions'
import { useToday, type RackRoom, type TodayBoard } from '../api'
import { ActivityPanel } from '../components/ActivityPanel'
import { CheckInDialog } from '../components/CheckInDialog'
import { CheckOutDialog } from '../components/CheckOutDialog'
import { KeyRack } from '../components/KeyRack'
import { TodayFigures } from '../components/TodayFigures'
import { WidgetZone } from '../components/WidgetZone'
import { firstName, partOfDay } from '../lib/greeting'
import { landingFor } from '../lib/home'
import type { KeyAction } from '../lib/rack'

type OpenDialog = { kind: 'checkin' | 'checkout'; stayId: string; reservationId: string }

const KEY_PERMISSION: Record<KeyAction['kind'], string | undefined> = {
  checkin: 'bookings.checkin',
  checkout: 'bookings.checkin',
  open: 'bookings.view',
  book: 'bookings.manage',
  calendar: 'bookings.view',
  none: undefined,
}

/**
 * `/app` — Today (plan C1), the home of the staff app: a calm command center for the business date.
 * People who do not run the front desk (no `frontdesk.view`) land on their own page instead
 * (housekeepers → `/app/housekeeping/mine`).
 */
export default function TodayPage() {
  const can = usePermissionChecker()
  const nav = useNav()
  const membership = useActiveMembership()
  const { t } = useTranslation('frontdesk')
  // Decide where someone lands only once their role is known (the shell renders pages after that anyway).
  if (!membership) return <LoadingState />
  const landing = landingFor(can, nav)
  if (landing) return <Navigate to={landing} replace />
  if (!can('frontdesk.view')) return <EmptyState title={t('today.noAccess')} description={t('today.noAccessHint')} />
  return <TodayView />
}

function TodayView() {
  const board = useToday()
  const widgets = useWidgets()
  const can = usePermissionChecker()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<OpenDialog | null>(null)

  function onKey(room: RackRoom, action: KeyAction) {
    const bd = board.data?.business_date
    switch (action.kind) {
      case 'checkin':
      case 'checkout':
        setDialog({ kind: action.kind, stayId: action.stayId, reservationId: action.reservationId })
        break
      case 'open':
        navigate(`/app/reservations/${action.reservationId}`)
        break
      case 'book': {
        const day = parseDate(bd) ?? new Date()
        const search = new URLSearchParams({
          checkin: toISODate(day),
          checkout: toISODate(addDays(day, 1)),
          room_id: room.id,
          room_type_id: room.room_type.id,
        })
        navigate(`/app/reservations/new?${search.toString()}`)
        break
      }
      case 'calendar':
        navigate('/app/calendar')
        break
      case 'none':
        break
    }
  }

  return (
    <div className="mx-auto grid max-w-[1400px] gap-6">
      <Greeting board={board.data} />
      {board.isError ? (
        <ErrorState error={board.error} onRetry={() => board.refetch()} className="rounded-xl border border-border bg-surface" />
      ) : !board.data ? (
        <BoardSkeleton />
      ) : (
        <>
          {board.data.night_audit.due && <AuditNotice board={board.data} canRun={can('frontdesk.night_audit')} />}
          <TodayFigures board={board.data} />
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
            <ActivityPanel
              board={board.data}
              onCheckIn={(row) => setDialog({ kind: 'checkin', stayId: row.stay_id, reservationId: row.reservation_id })}
              onCheckOut={(row) => setDialog({ kind: 'checkout', stayId: row.stay_id, reservationId: row.reservation_id })}
            />
            <KeyRack rooms={board.data.rooms} can={(kind) => can(KEY_PERMISSION[kind])} onAction={onKey} />
          </div>
        </>
      )}
      <WidgetZone widgets={widgets} />
      {dialog?.kind === 'checkin' && (
        <CheckInDialog open onOpenChange={(open) => !open && setDialog(null)} stayId={dialog.stayId} reservationId={dialog.reservationId} />
      )}
      {dialog?.kind === 'checkout' && (
        <CheckOutDialog open onOpenChange={(open) => !open && setDialog(null)} stayId={dialog.stayId} reservationId={dialog.reservationId} />
      )}
    </div>
  )
}

function Greeting({ board }: { board?: TodayBoard }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const { data: me } = useMe()
  const { property } = useActiveProperty()
  const can = usePermissionChecker()
  const day = board?.business_date ?? property?.business_date
  const name = firstName(me?.full_name)
  const part = partOfDay(new Date(), property?.timezone ?? 'America/Bogota')

  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {day && (
          <p className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-muted">
            <span aria-hidden className="size-2 rounded-full border border-border-strong bg-surface" />
            <span>{formatDate(day, lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", lang)}</span>
          </p>
        )}
        <h1 className="text-[28px] leading-9 tracking-[-0.03em] text-fg">
          {name ? t(`today.greeting.${part}`, { name }) : t(`today.greetingAnonymous.${part}`)}
        </h1>
      </div>
      {can('bookings.manage') && (
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild>
            <Link to="/app/reservations/new?walk_in=1">
              <DoorOpen aria-hidden />
              {t('actions.walkIn')}
            </Link>
          </Button>
          <Button asChild variant="primary">
            <Link to="/app/reservations/new">
              <Plus aria-hidden />
              {t('actions.newReservation')}
            </Link>
          </Button>
        </div>
      )}
    </header>
  )
}

function AuditNotice({ board, canRun }: { board: TodayBoard; canRun: boolean }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  return (
    <div
      role="status"
      aria-label={t('today.auditDueTitle')}
      className="flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning-soft/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2.5 text-[13px] text-warning-ink">
        <MoonStar aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span>
          <strong className="font-bold">{t('today.auditDueTitle')}.</strong>{' '}
          {t('today.auditDue', { date: formatDate(board.business_date, lang === 'en' ? 'MMM d' : 'd MMM', lang) })}
        </span>
      </p>
      {canRun && (
        <Button asChild size="sm" className="shrink-0">
          <Link to="/app/night-audit">{t('today.goToAudit')}</Link>
        </Button>
      )}
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div className="grid gap-6" aria-hidden>
      <Skeleton className="h-[132px] rounded-xl" />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <Skeleton className="h-80 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  )
}
