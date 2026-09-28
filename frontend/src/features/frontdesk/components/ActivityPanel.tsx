import type { TFunction } from 'i18next'
import { ArrowUpRight, CircleCheck, LogIn, LogOut, Plus, Star } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { MoneyText } from '@/components/Money'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { formatDate, normalizeLang, type Lang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { TodayBoard, TodayRow } from '../api'
import { guestsLabel, shortDay, tr, unitLabel } from '../lib/labels'

export type ActivityTab = 'arrivals' | 'departures' | 'in_house'

export interface ActivityPanelProps {
  board: TodayBoard
  onCheckIn: (row: TodayRow) => void
  onCheckOut: (row: TodayRow) => void
}

/**
 * Today's movements (plan C1): arrivals, departures and guests in house, one row per stay with what it needs
 * (room ready, balance, online check-in…) and its one action — check-in or check-out — a click away.
 * Rows already done stay at the bottom, quieter.
 */
export function ActivityPanel({ board, onCheckIn, onCheckOut }: ActivityPanelProps) {
  const { t } = useTranslation('frontdesk')
  const titleId = useId()
  const [tab, setTab] = useState<ActivityTab>('arrivals')
  const { kpis } = board

  return (
    <section aria-labelledby={titleId} className="min-w-0 rounded-xl border border-border bg-surface shadow-xs">
      <header className="flex items-baseline justify-between gap-3 px-5 pt-4">
        <h2 id={titleId} className="text-[15px] font-bold tracking-[-0.01em]">
          {t('activity.title')}
        </h2>
        <Link to={`/app/reservations?view=${tab}`} className="text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('activity.seeAll')}
        </Link>
      </header>
      <Tabs value={tab} onValueChange={(value) => setTab(value as ActivityTab)}>
        <TabsList className="px-5">
          <TabsTrigger value="arrivals">
            {t('activity.arrivals')}
            <Count done={kpis.arrivals_done} total={kpis.arrivals_total} />
          </TabsTrigger>
          <TabsTrigger value="departures">
            {t('activity.departures')}
            <Count done={kpis.departures_done} total={kpis.departures_total} />
          </TabsTrigger>
          <TabsTrigger value="in_house">
            {t('activity.inHouse')}
            <Count total={board.in_house.length} />
          </TabsTrigger>
        </TabsList>
        <TabsContent value="arrivals" className="pt-0">
          <Rows rows={board.arrivals} kind="arrivals" onCheckIn={onCheckIn} onCheckOut={onCheckOut} />
        </TabsContent>
        <TabsContent value="departures" className="pt-0">
          <Rows rows={board.departures} kind="departures" onCheckIn={onCheckIn} onCheckOut={onCheckOut} />
        </TabsContent>
        <TabsContent value="in_house" className="pt-0">
          <Rows rows={board.in_house} kind="in_house" onCheckIn={onCheckIn} onCheckOut={onCheckOut} />
        </TabsContent>
      </Tabs>
    </section>
  )
}

function Count({ done, total }: { done?: number; total: number }) {
  return (
    <span className="num rounded-full bg-surface-2 px-1.5 py-px text-[11px] font-bold text-muted">
      {done === undefined ? total : `${done}/${total}`}
    </span>
  )
}

function Rows({
  rows,
  kind,
  onCheckIn,
  onCheckOut,
}: {
  rows: TodayRow[]
  kind: ActivityTab
  onCheckIn: (row: TodayRow) => void
  onCheckOut: (row: TodayRow) => void
}) {
  const { t } = useTranslation('frontdesk')
  const canBook = useCan('bookings.manage')
  if (rows.length === 0) {
    return (
      <EmptyState
        title={t(`activity.empty.${kind}`)}
        action={
          kind === 'arrivals' && canBook ? (
            <Button asChild size="sm">
              <Link to="/app/reservations/new">
                <Plus aria-hidden />
                {t('actions.newReservation')}
              </Link>
            </Button>
          ) : undefined
        }
        className="py-10"
      />
    )
  }
  return (
    <ul className="divide-y divide-border">
      {rows.map((row) => (
        <ActivityRow key={`${kind}-${row.stay_id}`} row={row} kind={kind} onCheckIn={onCheckIn} onCheckOut={onCheckOut} />
      ))}
    </ul>
  )
}

interface Chip {
  key: string
  tone: BadgeTone
  text: string
  icon?: ReactNode
}

function chipsFor(row: TodayRow, kind: ActivityTab, t: TFunction, lang: Lang): Chip[] {
  const chips: Chip[] = []
  if (kind === 'arrivals') {
    if (row.done) chips.push({ key: 'in', tone: 'accent', text: t('chips.checkedIn') })
    if (row.ready) chips.push({ key: 'ready', tone: 'success', text: t('chips.ready') })
    for (const issue of row.issues) {
      if (issue === 'late_arrival') chips.push({ key: issue, tone: 'danger', text: t('chips.late', { date: shortDay(row.checkin, lang) }) })
      if (issue === 'tentative') chips.push({ key: issue, tone: 'warning', text: t('chips.tentative') })
      if (issue === 'unassigned') chips.push({ key: issue, tone: 'warning', text: t('chips.unassigned') })
      if (issue === 'room_occupied') chips.push({ key: issue, tone: 'warning', text: t('chips.roomOccupied') })
      if (issue === 'room_not_ready') chips.push({ key: issue, tone: 'warning', text: t(`chips.room_${row.room_status ?? 'dirty'}`) })
    }
    if (row.online_checkin_done && !row.done) {
      chips.push({ key: 'online', tone: 'info', text: t('chips.online'), icon: <CircleCheck aria-hidden /> })
    }
  } else {
    if (kind === 'departures' && row.done) chips.push({ key: 'out', tone: 'success', text: t('chips.checkedOut') })
    if (row.issues.includes('overdue')) chips.push({ key: 'overdue', tone: 'danger', text: t('chips.overdue', { date: shortDay(row.checkout, lang) }) })
    if (kind === 'in_house' && row.departs_today) chips.push({ key: 'today', tone: 'info', text: t('chips.leavesToday') })
    if (row.issues.includes('balance_due')) chips.push({ key: 'balance', tone: 'warning', text: t('chips.balanceDue') })
    if (kind === 'departures' && row.ready) chips.push({ key: 'settled', tone: 'success', text: t('chips.settled') })
  }
  return chips
}

function ActivityRow({
  row,
  kind,
  onCheckIn,
  onCheckOut,
}: {
  row: TodayRow
  kind: ActivityTab
  onCheckIn: (row: TodayRow) => void
  onCheckOut: (row: TodayRow) => void
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const nameId = useId()
  const canCheck = useCan('bookings.checkin')
  const unit = unitLabel(row.room, row.bed)
  const chips = chipsFor(row, kind, t, lang)
  const pendingArrival = kind === 'arrivals' && !row.done
  const leaving = row.status === 'checked_in' && (kind === 'departures' || (kind === 'in_house' && (row.departs_today || row.issues.includes('overdue'))))
  const balanceDue = Number(row.balance_due) > 0
  const doneAt = kind === 'arrivals' ? row.checked_in_at : kind === 'departures' ? row.checked_out_at : null

  return (
    <li aria-labelledby={nameId} className={cn('flex items-center gap-3 px-5 py-3 sm:gap-4', row.done && 'bg-surface-2/40')}>
      {unit ? (
        <RoomKeyTag
          number={unit}
          status={kind === 'arrivals' && !row.done && !row.occupied_by ? (row.room_status ?? 'clean') : 'occupied'}
          size="md"
          className={cn(row.done && 'opacity-70')}
        />
      ) : (
        <span
          aria-hidden
          className="inline-flex h-9 min-w-12 items-end justify-end rounded-md border border-dashed border-border-strong px-2 pb-1.5 text-xs font-bold text-subtle"
        >
          —
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="flex min-w-0 items-center gap-1.5">
          <span id={nameId} className={cn('truncate font-semibold', row.done ? 'text-muted' : 'text-fg')}>
            {row.guest_name}
          </span>
          {row.is_vip && <Star role="img" aria-label={t('vip')} className="size-3.5 shrink-0 fill-warning text-warning" />}
        </p>
        <p className="truncate text-[13px] text-muted">
          <Link to={`/app/reservations/${row.reservation_id}`} className="num font-semibold text-fg/80 underline-offset-4 hover:text-accent-ink hover:underline">
            {row.code}
          </Link>
          {' · '}
          {tr(row.room_type.name, i18n.language)} · {t('common:date.nights', { count: row.nights })} · {guestsLabel(t, row.adults, row.children)}
        </p>
        {chips.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {chips.map((chip) => (
              <Badge key={chip.key} tone={chip.tone}>
                {chip.icon}
                {chip.text}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="hidden shrink-0 text-right text-[13px] sm:block">
        {doneAt ? (
          <p className="num text-muted">{formatDate(doneAt, 'HH:mm', lang)}</p>
        ) : kind === 'arrivals' && row.eta ? (
          <p className="num text-fg">
            <span className="text-muted">{t('activity.eta')}</span> {row.eta}
          </p>
        ) : kind !== 'arrivals' ? (
          <p className="num text-muted">{t('activity.until', { date: shortDay(row.checkout, lang) })}</p>
        ) : null}
        <p className={cn('num', balanceDue ? 'font-semibold text-warning-ink' : 'text-muted')}>
          {balanceDue ? <MoneyText value={row.balance_due} /> : t('activity.noBalance')}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {canCheck && pendingArrival && (
          <Button size="sm" onClick={() => onCheckIn(row)}>
            <LogIn aria-hidden />
            {t('actions.checkIn')}
          </Button>
        )}
        {canCheck && leaving && (
          <Button size="sm" onClick={() => onCheckOut(row)}>
            <LogOut aria-hidden />
            {t('actions.checkOut')}
          </Button>
        )}
        <Button asChild variant="ghost" size="icon-sm">
          <Link to={`/app/reservations/${row.reservation_id}`} aria-label={t('activity.open', { code: row.code })}>
            <ArrowUpRight aria-hidden />
          </Link>
        </Button>
      </div>
    </li>
  )
}
