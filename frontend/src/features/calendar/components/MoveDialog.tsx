import { ArrowRight, CircleAlert, DoorOpen, RotateCw } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DatePicker, DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useCalendarData, type CalBed, type CalendarData, type CalRoom, type CalRoomType, type CalStay } from '../api'
import { SCROLL_DIALOG } from '../lib/constants'
import { addDays, diffDays } from '../lib/dates'
import { createPlanContext, planChange, type InvalidReason, type MoveTarget, type PlanResult } from '../lib/dnd'
import { indexRooms, invalidText, pick, placeLabel, type RoomIndex } from '../lib/labels'

/** `GET calendar/` answers at most 93 days: longer stays are checked here on their first 93 nights (the server checks all). */
const MAX_WINDOW_DAYS = 93
const NONE = 'none'
const EMPTY: CalendarData = { room_types: [], stays: [], blocks: [], availability: {} }
/** Problems of the dates themselves (not of one room): shown under the dates, and nothing can be chosen. */
const DATE_REASONS: ReadonlySet<InvalidReason> = new Set(['finished', 'min_one_night', 'in_house_arrival', 'in_house_departure', 'past_arrival'])

export interface MoveDialogProps {
  stay: CalStay | null
  businessDate: string
  onCancel: () => void
  /** What the chosen room and dates take (or why not): the same path as a drop on the grid. */
  onPlan: (stay: CalStay, result: PlanResult) => void
}

function keyOf(roomId: string | null, bedId: string | null): string {
  if (bedId) return `bed:${bedId}`
  if (roomId) return `room:${roomId}`
  return NONE
}

interface UnitOption {
  key: string
  room: CalRoom
  bed: CalBed | null
  target: MoveTarget
  result: PlanResult
  current: boolean
}

interface CategoryGroup {
  roomType: CalRoomType
  booked: boolean
  /** Private rooms: one option each. Dorms: the beds of each room. */
  rooms: { room: CalRoom; options: UnitOption[] }[]
}

/**
 * "Move" from the booking panel — the way to move on a phone, or without dragging: new dates and a room
 * (or bed) picked from the key rack of the category and, as an upgrade, of the others. Rooms taken, blocked
 * or without a sellable unit on those nights cannot be picked; the rack is read from the calendar of exactly
 * those nights. The choice then runs like a drop on the grid (confirmations included).
 */
export function MoveDialog({ stay, businessDate, onCancel, onPlan }: MoveDialogProps) {
  return (
    <Dialog open={stay !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className={cn(SCROLL_DIALOG.content, 'sm:max-w-xl')}>
        {stay && <MoveBody key={stay.id} stay={stay} businessDate={businessDate} onCancel={onCancel} onPlan={onPlan} />}
      </DialogContent>
    </Dialog>
  )
}

function MoveBody({ stay, businessDate, onCancel, onPlan }: Omit<MoveDialogProps, 'stay'> & { stay: CalStay }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const inHouse = stay.status === 'checked_in'
  const [range, setRange] = useState({ from: stay.checkin, to: stay.checkout })
  const [choice, setChoice] = useState(() => keyOf(stay.room_id, stay.bed_id))

  const windowEnd = diffDays(range.from, range.to) > MAX_WINDOW_DAYS ? addDays(range.from, MAX_WINDOW_DAYS) : range.to
  const windowQuery = useCalendarData(range.from, windowEnd)
  const data = windowQuery.isPlaceholderData ? undefined : windowQuery.data
  const ctx = useMemo(() => (data ? createPlanContext(data, businessDate) : null), [data, businessDate])
  const index = useMemo(() => indexRooms(data ?? EMPTY), [data])

  const { groups, noneResult, datesProblem } = useMemo(() => {
    if (!data || !ctx) return { groups: [] as CategoryGroup[], noneResult: null, datesProblem: null }
    const at = (roomTypeId: string, roomId: string | null, bedId: string | null): MoveTarget => ({
      roomTypeId,
      roomId,
      bedId,
      checkin: range.from,
      checkout: range.to,
    })
    const bookedType = data.room_types.find((roomType) => roomType.id === stay.room_type_id)
    const kind = bookedType?.kind ?? (stay.bed_id ? 'dorm' : 'private')
    const types = data.room_types
      .filter((roomType) => roomType.kind === kind)
      .sort((a, b) => Number(b.id === stay.room_type_id) - Number(a.id === stay.room_type_id))
    const option = (roomType: CalRoomType, room: CalRoom, bed: CalBed | null): UnitOption => {
      const target = at(roomType.id, room.id, bed?.id ?? null)
      return {
        key: keyOf(room.id, bed?.id ?? null),
        room,
        bed,
        target,
        result: planChange(stay, target, ctx),
        current: stay.room_id === room.id && (stay.bed_id ?? null) === (bed?.id ?? null),
      }
    }
    const built: CategoryGroup[] = types.map((roomType) => ({
      roomType,
      booked: roomType.id === stay.room_type_id,
      rooms: roomType.rooms
        .map((room) => ({
          room,
          options: kind === 'dorm' ? room.beds.map((bed) => option(roomType, room, bed)) : [option(roomType, room, null)],
        }))
        .filter((entry) => entry.options.length > 0),
    }))
    // Where it is now, with the new dates: tells problems of the dates apart from problems of one room.
    const here = planChange(stay, at(stay.room_type_id, stay.room_id, stay.bed_id), ctx)
    const problem = here.kind === 'invalid' && DATE_REASONS.has(here.reason) ? here : null
    return {
      groups: built,
      noneResult: inHouse ? null : planChange(stay, at(stay.room_type_id, null, null), ctx),
      datesProblem: problem,
    }
  }, [data, ctx, range, stay, inHouse])

  const options = groups.flatMap((group) => group.rooms.flatMap((entry) => entry.options))
  const selected = choice === NONE ? noneResult : (options.find((candidate) => candidate.key === choice)?.result ?? null)
  const selectedTarget = choice === NONE ? { roomId: null, bedId: null } : options.find((candidate) => candidate.key === choice)?.target
  const canSubmit = Boolean(ctx && !datesProblem && selected?.kind === 'plan')
  const loading = windowQuery.isPending || windowQuery.isPlaceholderData

  function submit() {
    if (!selected || !canSubmit) return
    onCancel()
    onPlan(stay, selected)
  }

  const minDeparture = addDays(stay.checkin, 1) > businessDate ? addDays(stay.checkin, 1) : businessDate

  return (
    <>
      <DialogHeader className={SCROLL_DIALOG.header}>
        <DialogTitle>{t('move.title')}</DialogTitle>
        <DialogDescription className="num">
          {stay.guest_name} · {stay.code} · {formatDateRange(stay.checkin, stay.checkout, lang)}
        </DialogDescription>
      </DialogHeader>

      {/* A big rack scrolls (a phone, a hotel of 40 rooms, a hostel of beds); the buttons stay in reach. */}
      <div className={SCROLL_DIALOG.body}>
        <div className="grid gap-1.5">
          <Label htmlFor={`move-dates-${stay.id}`}>{inHouse ? t('panel.departure') : t('move.dates')}</Label>
          {inHouse ? (
            <DatePicker
              id={`move-dates-${stay.id}`}
              value={range.to}
              min={minDeparture}
              onChange={(value) => value && setRange({ from: stay.checkin, to: value })}
            />
          ) : (
            <DateRangePicker
              id={`move-dates-${stay.id}`}
              value={range}
              onChange={(value) => value && setRange(value)}
              today={businessDate}
              min={businessDate}
              minNights={1}
              showNights
            />
          )}
          {inHouse && <p className="text-xs text-muted">{t('move.arrivalLocked')}</p>}
          {datesProblem && (
            <p role="alert" className="flex items-start gap-1.5 text-xs font-semibold text-danger-ink">
              <CircleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
              {invalidText(t, datesProblem, lang)}
            </p>
          )}
        </div>

        <div className="grid gap-2.5">
          <div className="flex items-baseline justify-between gap-3">
            <p id={`move-rack-${stay.id}`} className="text-[13px] leading-5 font-semibold text-fg">
              {t('move.room')}
            </p>
            {loading && data === undefined && !windowQuery.isError && (
              <span role="status" className="text-xs text-muted">
                {t('move.loadingRooms')}
              </span>
            )}
          </div>

          {windowQuery.isError ? (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-danger/30 bg-danger-soft/60 px-3.5 py-3 text-[13px] text-danger-ink">
              <span className="min-w-0 flex-1">{errorMessage(windowQuery.error, t)}</span>
              <Button size="sm" onClick={() => void windowQuery.refetch()}>
                <RotateCw aria-hidden />
                {t('actions.retry', { ns: 'common' })}
              </Button>
            </div>
          ) : !data ? (
            <RackSkeleton />
          ) : (
            <RadioGroupPrimitive.Root
              value={choice}
              onValueChange={setChoice}
              aria-labelledby={`move-rack-${stay.id}`}
              disabled={Boolean(datesProblem)}
              loop
              className="grid gap-4"
            >
              {noneResult && (
                <RadioGroupPrimitive.Item
                  value={NONE}
                  disabled={noneResult.kind === 'invalid'}
                  className={cn(
                    'flex items-center gap-2.5 justify-self-start rounded-lg border border-dashed px-3 py-2 text-left text-[13px] font-semibold transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:opacity-45',
                    choice === NONE ? 'border-accent bg-accent-soft/60 text-accent-ink' : 'border-border-strong text-muted hover:border-accent/60 hover:text-fg',
                  )}
                >
                  <DoorOpen aria-hidden className="size-4 shrink-0" />
                  {t('move.noRoom')}
                  {stay.room_id === null && <span className="text-2xs font-bold tracking-wide uppercase opacity-80">· {t('move.here')}</span>}
                </RadioGroupPrimitive.Item>
              )}
              {groups.map((group) => (
                <CategoryRack key={group.roomType.id} group={group} choice={choice} lang={lang} index={index} arrivesNow={range.from <= businessDate} />
              ))}
            </RadioGroupPrimitive.Root>
          )}
        </div>

        {selected?.kind === 'invalid' && !datesProblem && (
          <p role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft/70 px-3.5 py-2.5 text-[13px] text-danger-ink">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {invalidText(t, selected, lang)}
          </p>
        )}
        {selected?.kind === 'plan' && selectedTarget && (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-surface-2/70 px-3.5 py-2.5 text-[13px] text-muted">
            <ArrowRight aria-hidden className="size-4 text-accent" />
            <span className="font-semibold text-fg">{placeLabel(t, index, selectedTarget.roomId ?? null, selectedTarget.bedId ?? null)}</span>
            <span className="num">{formatDateRange(range.from, range.to, lang)}</span>
          </p>
        )}
      </div>

      <DialogFooter className={SCROLL_DIALOG.footer}>
        <Button onClick={onCancel}>{t('actions.cancel', { ns: 'common' })}</Button>
        <Button variant="primary" disabled={!canSubmit} onClick={submit}>
          {t('move.submit')}
        </Button>
      </DialogFooter>
    </>
  )
}

/** One category of the key rack: its rooms as key tags (dorms: each room's beds), the booked one first. */
function CategoryRack({
  group,
  choice,
  lang,
  index,
  arrivesNow,
}: {
  group: CategoryGroup
  choice: string
  lang: Lang
  index: RoomIndex
  arrivesNow: boolean
}) {
  const { t } = useTranslation('calendar')
  const name = pick(group.roomType.name, lang)
  const dorm = group.roomType.kind === 'dorm'
  return (
    <section aria-label={name} className="grid gap-2">
      <h3 className="flex items-center gap-2 text-xs font-bold text-fg">
        <span aria-hidden className="h-3.5 w-1 rounded-full" style={{ background: group.roomType.color }} />
        {name}
        <span
          className={cn(
            'rounded-full px-1.5 py-px text-2xs font-bold tracking-wide uppercase',
            group.booked ? 'bg-surface-2 text-muted' : 'bg-info-soft text-info-ink',
          )}
        >
          {group.booked ? t('move.booked') : t('move.upgrade')}
        </span>
      </h3>
      {dorm ? (
        <div className="grid gap-2.5">
          {group.rooms.map(({ room, options }) => (
            <div key={room.id} className="grid gap-1.5">
              <p className="text-2xs font-semibold text-muted">{t('grid.rowDorm', { number: room.number })}</p>
              <div className="flex flex-wrap gap-1.5">
                {options.map((option) => (
                  <RackKey
                    key={option.key}
                    option={option}
                    selected={choice === option.key}
                    label={option.bed?.label ?? room.number}
                    lang={lang}
                    index={index}
                    arrivesNow={arrivesNow}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {group.rooms.flatMap(({ room, options }) =>
            options.map((option) => (
              <RackKey key={option.key} option={option} selected={choice === option.key} label={room.number} lang={lang} index={index} arrivesNow={arrivesNow} />
            )),
          )}
        </div>
      )}
    </section>
  )
}

/**
 * A room (or bed) of the rack: its key tag in the housekeeping color and a one-word state underneath. Whether
 * a free room is ready (clean) only matters for a guest arriving today or already in house.
 */
function RackKey({ option, selected, label, lang, index, arrivesNow }: { option: UnitOption; selected: boolean; label: string; lang: Lang; index: RoomIndex; arrivesNow: boolean }) {
  const { t } = useTranslation('calendar')
  const { result, room, current } = option
  const invalid = result.kind === 'invalid'
  const status = room.housekeeping_status
  let caption: string
  let tone: string
  if (current) {
    caption = t('move.here')
    tone = 'text-accent-ink'
  } else if (result.kind === 'invalid') {
    caption = result.reason === 'blocked' ? t('move.blocked') : result.reason === 'no_units' ? t('move.noUnits') : t('move.taken')
    tone = 'text-subtle'
  } else if (status === 'out_of_service' || (arrivesNow && status === 'dirty')) {
    caption = t(`status.room.${status}`, { ns: 'common', defaultValue: status }).toLocaleLowerCase(lang)
    tone = 'text-warning-ink'
  } else {
    caption = arrivesNow ? t('move.ready') : t('move.free')
    tone = 'text-success-ink'
  }
  const place = placeLabel(t, index, option.target.roomId, option.target.bedId)
  const reason = result.kind === 'invalid' ? invalidText(t, result, lang) : undefined
  return (
    <RadioGroupPrimitive.Item
      value={option.key}
      disabled={invalid && !current}
      aria-label={`${place} · ${reason ?? caption}`}
      title={reason ?? caption}
      className={cn(
        'group/key grid w-[4.25rem] justify-items-center gap-1 rounded-lg border px-1 pt-1.5 pb-1 transition-[border-color,background-color,box-shadow]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:cursor-not-allowed',
        selected ? 'border-accent bg-accent-soft/55 shadow-xs' : 'border-transparent hover:border-border-strong hover:bg-surface-2/70',
        invalid && !current && 'opacity-55',
      )}
    >
      <RoomKeyTag number={label} status={status} inactive={invalid && !current} size="md" />
      <span className={cn('max-w-full truncate text-2xs leading-4 font-semibold', tone)}>{caption}</span>
    </RadioGroupPrimitive.Item>
  )
}

function RackSkeleton() {
  return (
    <div aria-hidden className="grid gap-2">
      <Skeleton className="h-3.5 w-32" />
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="grid w-[4.25rem] justify-items-center gap-1 px-1 pt-1.5 pb-1">
            <Skeleton className="h-9 w-12" />
            <Skeleton className="h-3 w-10" />
          </div>
        ))}
      </div>
    </div>
  )
}
