import { BedDouble, FilterX, Plus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import type { GridResponse } from '@/features/rates/api'
import { useActiveProperty } from '@/lib/auth'
import { normalizeLang } from '@/lib/format'
import { useLocalStorageState } from '@/lib/hooks'
import { useCan } from '@/lib/permissions'
import { calendarKeys, useCalendarData, useCalendarPrices, useHolidayList, type CalendarData, type CalStay, type StayStatus } from '../api'
import { CalendarGrid, type CalendarGridHandle } from '../components/CalendarGrid'
import { CalendarLegend } from '../components/CalendarLegend'
import { CalendarToolbar } from '../components/CalendarToolbar'
import { CategoryDialog, DatesDialog, type ChangeRequest } from '../components/ChangeDialogs'
import { CreateDialog } from '../components/CreateDialog'
import type { PriceIndex } from '../components/GridRow'
import { MoveDialog } from '../components/MoveDialog'
import { StayPanel } from '../components/StayPanel'
import { useCalendarChanges } from '../hooks/useCalendarChanges'
import { useCollapsedState } from '../hooks/useCollapsedState'
import { SPANS, STATUSES } from '../lib/constants'
import { addDays, yearsBetween } from '../lib/dates'
import { createPlanContext, planChange, type MoveTarget, type PlanOption, type PlanResult } from '../lib/dnd'
import { indexRooms, invalidText, matchesSearch } from '../lib/labels'
import { buildRows, defaultCollapsed } from '../lib/layout'
import { calendarToast } from '../lib/toast'

const SPAN_STORAGE_KEY = 'housetel.calendar.span'
const NO_KEYS: ReadonlySet<string> = new Set()
const EMPTY_DATA: CalendarData = { room_types: [], stays: [], blocks: [], availability: {} }

function priceIndex(grid: GridResponse | undefined): PriceIndex | null {
  if (!grid?.rate_plan) return null
  return {
    planName: grid.rate_plan.name,
    currency: grid.currency,
    byRoomType: new Map(
      grid.room_types.map((roomType) => [roomType.id, new Map(roomType.rows.map((row) => [row.date, { price: row.price, stop_sell: row.stop_sell }]))]),
    ),
  }
}

/**
 * `/app/calendar`: rooms, dorm beds and bookings day by day. Starts the day before the business date of the
 * active property (never the device date) and starts over when the property changes.
 */
export default function CalendarPage() {
  const { property } = useActiveProperty()
  if (!property) return <LoadingState variant="rows" rows={10} />
  return <Calendar key={property.id} businessDate={property.business_date} />
}

function Calendar({ businessDate }: { businessDate: string }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('bookings.manage')
  const canSeeRates = useCan('rates.view')
  const canSetUpRooms = useCan('inventory.view')

  const homeStart = addDays(businessDate, -1)
  const [start, setStart] = useState(homeStart)
  const [storedSpan, setSpan] = useLocalStorageState<number>(SPAN_STORAGE_KEY, 14)
  const span = (SPANS as readonly number[]).includes(storedSpan) ? storedSpan : 14
  const end = addDays(start, span)

  // One day earlier than what is on screen: a guest leaving on the first day still shows that morning.
  const calendar = useCalendarData(addDays(start, -1), end)
  const pricesQuery = useCalendarPrices(start, end, lang, canSeeRates)
  const years = yearsBetween(start, end)
  const firstYear = useHolidayList(years[0], lang, canSeeRates)
  const lastYear = useHolidayList(years[years.length - 1], lang, canSeeRates)

  const [categories, setCategories] = useState<Set<string>>(() => new Set())
  const [statuses, setStatuses] = useState<Set<StayStatus>>(() => new Set(STATUSES))
  const [search, setSearch] = useState('')
  const gridRef = useRef<CalendarGridHandle>(null)
  const matchCursor = useRef(-1)

  const data = calendar.data
  const defaults = useMemo(() => (data ? defaultCollapsed(data, { rangeStart: start, days: span }) : NO_KEYS), [data, start, span])
  const { collapsed, toggle, setFolded } = useCollapsedState(defaults)
  const rows = useMemo(
    () => (data ? buildRows(data, { rangeStart: start, days: span, collapsed, categories, statuses }) : []),
    [data, start, span, collapsed, categories, statuses],
  )
  const ctx = useMemo(() => createPlanContext(data ?? EMPTY_DATA, businessDate), [data, businessDate])
  const index = useMemo(() => indexRooms(data ?? EMPTY_DATA), [data])
  const prices = useMemo(() => priceIndex(pricesQuery.data), [pricesQuery.data])
  const holidays = useMemo(
    () => new Map([...(firstYear.data ?? []), ...(lastYear.data ?? [])].map((holiday) => [holiday.date, holiday.name])),
    [firstYear.data, lastYear.data],
  )

  // Search matches in the order of the grid (top to bottom, then left to right), folded groups included:
  // the rows as they would be with everything unfolded and the current filters.
  const matchList = useMemo(() => {
    if (!data || !search.trim()) return []
    const found: { stay: CalStay; groups: string[] }[] = []
    const seen = new Set<string>()
    for (const row of buildRows(data, { rangeStart: start, days: span, categories, statuses })) {
      for (const item of row.items) {
        if (item.type !== 'stay' || seen.has(item.id) || !matchesSearch(item.stay, search)) continue
        seen.add(item.id)
        found.push({ stay: item.stay, groups: [`rt:${row.roomType.id}`, ...(row.kind === 'unassigned' ? [`un:${row.roomType.id}`] : [])] })
      }
    }
    return found
  }, [data, search, start, span, categories, statuses])
  const matches = useMemo(() => (search.trim() ? new Set(matchList.map((match) => match.stay.id)) : null), [matchList, search])

  // A match inside a folded group: unfold it, then focus the bar once its row is on the grid.
  const pendingFocus = useRef<string | null>(null)
  useEffect(() => {
    const stayId = pendingFocus.current
    if (!stayId || !rows.some((row) => row.items.some((item) => item.id === stayId))) return
    pendingFocus.current = null
    gridRef.current?.focusStay(stayId)
  }, [rows])

  function goToNextMatch() {
    if (matchList.length === 0) return
    matchCursor.current = (matchCursor.current + 1) % matchList.length
    const { stay, groups } = matchList[matchCursor.current]
    const folded = groups.filter((key) => collapsed.has(key))
    if (folded.length === 0) {
      gridRef.current?.focusStay(stay.id)
      return
    }
    pendingFocus.current = stay.id
    setFolded(folded, false)
  }

  // The open booking follows the grid's data, so a refetch after an action updates the panel too.
  const [openStayId, setOpenStayId] = useState<string | null>(null)
  const openStay = (stay: CalStay) => setOpenStayId(stay.id)
  const panelStay = (openStayId && data?.stays.find((stay) => stay.id === openStayId)) || null
  // "Move…" from the panel (the way to move on a phone): the panel gives way to the room picker.
  const [moving, setMoving] = useState<CalStay | null>(null)
  function moveStay(stay: CalStay) {
    setOpenStayId(null)
    setMoving(stay)
  }

  // Drops, dialogs and panel actions all end here: refuse, do nothing, run at once or ask first.
  const runChange = useCalendarChanges({ queryKey: calendarKeys.range(addDays(start, -1), end), ctx, index })
  const [request, setRequest] = useState<ChangeRequest | null>(null)
  function handlePlan(stay: CalStay, result: PlanResult) {
    if (result.kind === 'noop') return
    if (result.kind === 'invalid') {
      calendarToast.error(invalidText(t, result, lang))
      return
    }
    const { plan } = result
    if (plan.confirm === 'none' && plan.primary) void runChange(stay, plan, plan.primary)
    else setRequest({ stay, plan })
  }
  function confirmChange(confirmed: ChangeRequest, option: PlanOption) {
    setRequest(null)
    void runChange(confirmed.stay, confirmed.plan, option)
  }
  function unassignStay(stay: CalStay) {
    handlePlan(stay, planChange(stay, { roomTypeId: stay.room_type_id, roomId: null, bedId: null, checkin: stay.checkin, checkout: stay.checkout }, ctx))
  }

  // Days drawn over an empty stretch of a row: the quick booking dialog, already placed there.
  const [draft, setDraft] = useState<MoveTarget | null>(null)
  function handleCreate(next: MoveTarget) {
    if (!canManage) return
    setOpenStayId(null)
    setDraft(next)
  }

  const filtersActive = categories.size > 0 || statuses.size < STATUSES.length

  return (
    <div className="grid min-w-0 gap-4">
      <PageHeader
        title={t('page.title')}
        description={canManage ? t('page.description') : t('page.descriptionReadOnly')}
        className="pb-2"
        actions={
          canManage && (
            <Button asChild variant="primary">
              <Link to="/app/reservations/new">
                <Plus aria-hidden />
                {t('page.newReservation')}
              </Link>
            </Button>
          )
        }
      />

      <CalendarToolbar
        start={start}
        homeStart={homeStart}
        span={span}
        onStart={setStart}
        onSpan={setSpan}
        roomTypes={data?.room_types ?? []}
        categories={categories}
        onCategories={setCategories}
        statuses={statuses}
        onStatuses={setStatuses}
        search={search}
        onSearch={(value) => {
          matchCursor.current = -1
          setSearch(value)
        }}
        matchCount={matchList.length}
        onNextMatch={goToNextMatch}
        refreshing={calendar.isPlaceholderData || (calendar.isFetching && !calendar.isPending)}
      />

      {calendar.isPending ? (
        <LoadingState variant="rows" rows={10} />
      ) : calendar.isError || !data ? (
        <ErrorState error={calendar.error} onRetry={() => void calendar.refetch()} />
      ) : data.room_types.length === 0 ? (
        <EmptyState
          icon={BedDouble}
          title={t('page.noRooms')}
          description={t('page.noRoomsHint')}
          action={
            canSetUpRooms && (
              <Button asChild variant="primary">
                <Link to="/app/settings/rooms">{t('page.setUpRooms')}</Link>
              </Button>
            )
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FilterX}
          title={t('page.noMatches')}
          action={
            filtersActive && (
              <Button
                onClick={() => {
                  setCategories(new Set())
                  setStatuses(new Set(STATUSES))
                }}
              >
                {t('page.clearFilters')}
              </Button>
            )
          }
        />
      ) : (
        <CalendarGrid
          ref={gridRef}
          data={data}
          rows={rows}
          rangeStart={start}
          days={span}
          businessDate={businessDate}
          holidays={holidays}
          prices={prices}
          ctx={ctx}
          index={index}
          canManage={canManage}
          matches={matches}
          suppressClickCreate={openStayId !== null}
          onToggle={toggle}
          onOpen={openStay}
          onPlan={handlePlan}
          onCreate={handleCreate}
        />
      )}

      <CalendarLegend canManage={canManage} />

      <StayPanel
        stay={panelStay}
        index={index}
        businessDate={businessDate}
        onClose={() => setOpenStayId(null)}
        onMove={moveStay}
        onUnassign={unassignStay}
      />
      <MoveDialog stay={moving} businessDate={businessDate} onCancel={() => setMoving(null)} onPlan={handlePlan} />
      <CreateDialog draft={draft} ctx={ctx} index={index} roomTypes={data?.room_types ?? []} businessDate={businessDate} onClose={() => setDraft(null)} />
      <DatesDialog request={request?.plan.confirm === 'dates' ? request : null} index={index} onCancel={() => setRequest(null)} onConfirm={confirmChange} />
      <CategoryDialog request={request?.plan.confirm === 'category' ? request : null} index={index} onCancel={() => setRequest(null)} onConfirm={confirmChange} />
    </div>
  )
}
