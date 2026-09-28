import {
  DndContext,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { defaultRangeExtractor, observeElementRect, useVirtualizer, type Range, type Virtualizer } from '@tanstack/react-virtual'
import { Plus } from 'lucide-react'
import { memo, useCallback, useEffect, useId, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type Ref } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, formatDateRange, normalizeLang, type Lang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import type { CalendarData, CalStay } from '../api'
import { useElementWidth } from '../hooks/useElementWidth'
import { addDays, dayList, diffDays, isWeekendNight } from '../lib/dates'
import {
  checkCreate,
  keyboardDelta,
  previewDrop,
  resolveMove,
  roundDays,
  targetForRow,
  type CreateCheck,
  type DragMode,
  type DropPreview,
  type MoveTarget,
  type PlanContext,
  type PlanResult,
} from '../lib/dnd'
import { invalidText, newPlaceLabel, nightsOf, targetLabel, type RoomIndex } from '../lib/labels'
import { barMetrics, dayWidthFor, stayColumns, totalHeight, type CalendarRow, type StayItem } from '../lib/layout'
import { calendarToast } from '../lib/toast'
import type { BarDragData } from './StayBar'
import { GridRow, type PriceIndex, type RowHandlers } from './GridRow'

/** Height of the sticky row of day headers (px). */
export const HEADER_HEIGHT = 56
const LABEL_WIDTH = { phone: 104, wide: 212 } as const
/** A click right after a drag ends is the release of that drag, not a request to open the booking. */
const CLICK_AFTER_DRAG_MS = 300
/** A finger that travels farther than this is scrolling the grid, not tapping a day. */
const TAP_TOLERANCE_PX = 10
/** Mouse drags start after 5 px; on touch screens a bar is picked up with a long press (a swipe scrolls). */
const MOUSE_SENSOR = { activationConstraint: { distance: 5 } }
const TOUCH_SENSOR = { activationConstraint: { delay: 280, tolerance: 8 } }

/** dnd-kit speaks for pointer drags itself; the grid has its own live region for both pointer and keyboard. */
const SILENT: Announcements = {
  onDragStart: () => undefined,
  onDragMove: () => undefined,
  onDragOver: () => undefined,
  onDragEnd: () => undefined,
  onDragCancel: () => undefined,
}

export interface CalendarGridHandle {
  /** Scrolls a stay into view and focuses its bar (search → "go to the next one"). */
  focusStay: (stayId: string) => void
}

export interface CalendarGridProps {
  data: CalendarData
  rows: CalendarRow[]
  rangeStart: string
  days: number
  businessDate: string
  holidays: ReadonlyMap<string, string>
  prices: PriceIndex | null
  ctx: PlanContext
  index: RoomIndex
  canManage: boolean
  /** Stay ids matching the search (`null`: no search). */
  matches: ReadonlySet<string> | null
  /**
   * A booking panel is open: a plain click on an empty day only closes it (drawing over several days still
   * creates a booking).
   */
  suppressClickCreate: boolean
  onToggle: (key: string) => void
  onOpen: (stay: CalStay) => void
  /** A bar was dropped (pointer or keyboard): what it would take, for the page to confirm and run. */
  onPlan: (stay: CalStay, result: PlanResult) => void
  /** Empty days were drawn (or tapped): a new booking there, already checked against the grid. */
  onCreate: (draft: MoveTarget) => void
  ref?: Ref<CalendarGridHandle>
}

interface GridHandlers extends RowHandlers {
  /** Abandons a drawing in progress (and stops listening to the window). */
  stopDrawing: () => void
  dragStart: (event: DragStartEvent) => void
  dragMove: (event: DragMoveEvent) => void
  dragEnd: (event: DragEndEvent) => void
  dragCancel: () => void
}

/** A bar being moved: picked up with the pointer (dnd-kit) or with M (keyboard); `delta` is in px. */
interface DragSession {
  stay: CalStay
  rowIndex: number
  lane: number
  mode: DragMode
  delta: { x: number; y: number }
  source: 'pointer' | 'keyboard'
}

/** Days being drawn on an empty stretch of a row to create a booking there (columns of the range). */
interface CreateSession {
  rowIndex: number
  rowKey: string
  anchor: number
  current: number
  pointerId: number
  pointerType: string
  startX: number
  startY: number
  /** The pointer left the first day: a drag, not a click. */
  moved: boolean
  suppressClick: boolean
}

/** Until the scroll box is laid out (jsdom, first paint) assume it is as tall as the window. */
function observeRectOrWindow(instance: Virtualizer<HTMLDivElement, Element>, callback: (rect: { width: number; height: number }) => void) {
  return observeElementRect(instance, (rect) =>
    callback(rect.height > 0 ? rect : { width: rect.width || window.innerWidth, height: window.innerHeight }),
  )
}

/** Snapped position of a drag: only a change of row, day or departure re-renders the ghost. */
function snapKey(session: DragSession, rows: readonly CalendarRow[], dayWidth: number): string {
  if (session.mode === 'resize') return `r${roundDays(session.delta.x, dayWidth)}`
  const landing = resolveMove(rows, dayWidth, session.rowIndex, session.lane, session.delta)
  return landing ? `${landing.rowIndex}:${landing.dayDelta}` : 'out'
}

/** The booking a drawing stands for: the row's place and the nights from the first to the last day drawn. */
function draftOf(session: CreateSession, rows: readonly CalendarRow[], rangeStart: string): MoveTarget | null {
  const row = rows[session.rowIndex]
  const place = row && row.key === session.rowKey ? targetForRow(row) : null
  if (!place) return null
  const first = Math.min(session.anchor, session.current)
  const last = Math.max(session.anchor, session.current)
  return { ...place, checkin: addDays(rangeStart, first), checkout: addDays(rangeStart, last + 1) }
}

/**
 * The booking grid: rooms (and dorm beds) down, days across, one scroll box with sticky day headers and a
 * sticky room column. Rows are virtualized (TanStack Virtual) and every row height is known in advance
 * (`buildRows`), so 100+ units × 30 days stay fluid. Weekends and holidays are shaded column stripes; the
 * terracotta line of today sits mid-column, exactly where today's departures end and today's arrivals start.
 *
 * Bars move with @dnd-kit (mouse, or a long press on touch screens) or with the keyboard (M, arrows, Enter);
 * while moving, a ghost shows where the booking would land — red, with the reason, where it cannot go.
 * Drawing over empty days of a row (or tapping one on a phone) proposes a new booking there.
 */
export function CalendarGrid(props: CalendarGridProps) {
  const { data, rows, rangeStart, days, businessDate, holidays, prices, index, canManage, matches } = props
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const isPhone = useMediaQuery('(max-width: 639px)')
  const labelWidth = isPhone ? LABEL_WIDTH.phone : LABEL_WIDTH.wide
  const [setScrollElement, measuredWidth, scrollElement] = useElementWidth<HTMLDivElement>()
  const dayWidth = dayWidthFor(measuredWidth, days, labelWidth)
  const dates = useMemo(() => dayList(rangeStart, days), [rangeStart, days])
  const contentWidth = labelWidth + days * dayWidth
  const instructionsId = useId()

  const [session, setSession] = useState<DragSession | null>(null)
  const [creating, setCreating] = useState<CreateSession | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const sessionRef = useRef<DragSession | null>(null)
  const creatingRef = useRef<CreateSession | null>(null)
  const snapRef = useRef('')
  const dragEndedAt = useRef(0)

  // The row a drag started from stays mounted while it is scrolled away: its bar holds the focus (keyboard)
  // or is dnd-kit's active node (pointer); a drawing reads the days of its row.
  const pinned = session?.rowIndex ?? creating?.rowIndex ?? null
  const rangeExtractor = useCallback(
    (range: Range) => {
      const indexes = defaultRangeExtractor(range)
      return pinned === null || indexes.includes(pinned) ? indexes : [...indexes, pinned].sort((a, b) => a - b)
    },
    [pinned],
  )
  const getItemKey = useCallback((i: number) => rows[i]?.key ?? i, [rows])
  const estimateSize = useCallback((i: number) => rows[i]?.height ?? 40, [rows])
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollElement,
    estimateSize,
    getItemKey,
    overscan: 8,
    scrollMargin: HEADER_HEIGHT,
    observeElementRect: observeRectOrWindow,
    rangeExtractor,
  })

  const preview: DropPreview | null = useMemo(
    () =>
      session
        ? previewDrop(session.stay, { rowIndex: session.rowIndex, lane: session.lane }, session.delta, session.mode, rows, dayWidth, props.ctx)
        : null,
    [session, rows, dayWidth, props.ctx],
  )
  // Only mouse and pen drawings live in state (a finger's tap is known when it lifts).
  const draft = useMemo(() => (creating ? draftOf(creating, rows, rangeStart) : null), [creating, rows, rangeStart])
  const draftCheck: CreateCheck | null = useMemo(() => (draft ? checkCreate(draft, props.ctx) : null), [draft, props.ctx])

  // Handlers given to the (memoized) rows never change; they read the latest props and geometry here.
  const latest = useRef({ props, dayWidth, scrollElement })
  useLayoutEffect(() => {
    latest.current = { props, dayWidth, scrollElement }
  })

  const handlers = useMemo<GridHandlers>(() => {
    const language = () => normalizeLang(i18n.language)
    const updateSession = (next: DragSession | null) => {
      sessionRef.current = next
      snapRef.current = next ? snapKey(next, latest.current.props.rows, latest.current.dayWidth) : ''
      setSession(next)
    }
    const previewOf = (current: DragSession) =>
      previewDrop(
        current.stay,
        { rowIndex: current.rowIndex, lane: current.lane },
        current.delta,
        current.mode,
        latest.current.props.rows,
        latest.current.dayWidth,
        latest.current.props.ctx,
      )
    const describe = (next: DropPreview | null) => {
      if (!next?.target) return ''
      const { props: current } = latest.current
      const lng = language()
      const text = t('dnd.target', {
        place: targetLabel(t, lng, current.index, next.target),
        range: formatDateRange(next.target.checkin, next.target.checkout, lng),
      })
      return next.result?.kind === 'invalid' ? `${text} ${invalidText(t, next.result, lng)}` : text
    }
    const drop = (current: DragSession) => {
      const result = previewOf(current)?.result ?? null
      updateSession(null)
      if (!result || result.kind === 'noop') {
        setAnnouncement(t('dnd.cancel'))
        return
      }
      setAnnouncement(result.kind === 'invalid' ? invalidText(t, result, language()) : t('dnd.end'))
      latest.current.props.onPlan(current.stay, result)
    }
    const cancel = () => {
      updateSession(null)
      setAnnouncement(t('dnd.cancel'))
    }

    // ---- Drawing a new booking over empty days (plain pointer events; bars keep dnd-kit) ----
    /** Day column under `clientX` in the drawn row, read from the row as it is on screen now. */
    const columnAt = (drawing: CreateSession, clientX: number): number => {
      const { scrollElement: box, dayWidth: width, props: current } = latest.current
      const content = box?.querySelector<HTMLElement>(`[data-row-key="${drawing.rowKey}"] [data-row-content]`)
      if (!content) return drawing.current
      const column = Math.floor((clientX - content.getBoundingClientRect().left) / width)
      return Math.min(current.days - 1, Math.max(0, column))
    }
    const stopListening = () => {
      window.removeEventListener('pointermove', onDrawMove)
      window.removeEventListener('pointerup', onDrawEnd)
      window.removeEventListener('pointercancel', onDrawCancel)
    }
    const setDrawing = (next: CreateSession | null) => {
      creatingRef.current = next
      setCreating(next)
    }
    function onDrawMove(event: PointerEvent) {
      const drawing = creatingRef.current
      if (!drawing || event.pointerId !== drawing.pointerId) return
      if (drawing.pointerType === 'touch') {
        // Fingers scroll the grid: only a tap (no travel) proposes a booking.
        if (Math.hypot(event.clientX - drawing.startX, event.clientY - drawing.startY) > TAP_TOLERANCE_PX) onDrawCancel()
        return
      }
      const column = columnAt(drawing, event.clientX)
      if (column !== drawing.current) setDrawing({ ...drawing, current: column, moved: true })
    }
    function onDrawEnd(event: PointerEvent) {
      const drawing = creatingRef.current
      if (!drawing || event.pointerId !== drawing.pointerId) return
      stopListening()
      setDrawing(null)
      if (drawing.suppressClick && !drawing.moved) return
      const { props: current } = latest.current
      const target = draftOf(drawing, current.rows, current.rangeStart)
      if (!target) return
      const check = checkCreate(target, current.ctx)
      if (check.kind === 'invalid') {
        const text = invalidText(t, check, language())
        setAnnouncement(text)
        calendarToast.error(text)
        return
      }
      current.onCreate(target)
    }
    function onDrawCancel() {
      stopListening()
      setDrawing(null)
    }

    return {
      onToggle: (key) => latest.current.props.onToggle(key),
      onOpen: (stay) => {
        if (Date.now() - dragEndedAt.current < CLICK_AFTER_DRAG_MS) return
        latest.current.props.onOpen(stay)
      },
      onBarKeyDown: (event, item: StayItem, rowIndex: number) => {
        const current = sessionRef.current
        if (current?.source === 'keyboard' && current.stay.id === item.id) {
          if (event.key.startsWith('Arrow')) {
            event.preventDefault()
            const delta = keyboardDelta(latest.current.props.rows, latest.current.dayWidth, current, current.delta, event.key, current.mode)
            if (!delta) return
            const next = { ...current, delta }
            updateSession(next)
            setAnnouncement(describe(previewOf(next)))
          } else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            drop(current)
          } else if (event.key === 'Escape') {
            event.preventDefault()
            cancel()
          } else if (event.key === 'Tab') {
            cancel()
          }
          return
        }
        if (event.code !== 'KeyM' || event.altKey || event.ctrlKey || event.metaKey) return
        const { props: current2 } = latest.current
        const { stay } = item
        if (!current2.canManage || stay.status === 'checked_out') return
        const mode: DragMode = event.shiftKey ? 'resize' : 'move'
        if (mode === 'resize' && stay.checkout < current2.businessDate) return
        event.preventDefault()
        updateSession({ stay, rowIndex, lane: item.lane, mode, delta: { x: 0, y: 0 }, source: 'keyboard' })
        setAnnouncement(t('dnd.start', { guest: stay.guest_name }))
      },
      onBarBlur: (item: StayItem) => {
        const current = sessionRef.current
        if (current?.source === 'keyboard' && current.stay.id === item.id) cancel()
      },
      onContentPointerDown: (event, rowIndex) => {
        const { props: current } = latest.current
        if (!current.canManage || event.button !== 0 || sessionRef.current || creatingRef.current) return
        if ((event.target as Element).closest('[data-bar],[data-block]')) return
        const row = current.rows[rowIndex]
        if (!row || !targetForRow(row)) return
        const drawing: CreateSession = {
          rowIndex,
          rowKey: row.key,
          anchor: 0,
          current: 0,
          pointerId: event.pointerId,
          pointerType: event.pointerType,
          startX: event.clientX,
          startY: event.clientY,
          moved: false,
          suppressClick: current.suppressClickCreate,
        }
        const column = columnAt(drawing, event.clientX)
        drawing.anchor = column
        drawing.current = column
        if (event.pointerType !== 'touch') event.preventDefault() // no text selection while drawing
        creatingRef.current = drawing
        // Mouse and pen draw at once; a finger only shows the draft once it is a tap (see onDrawEnd).
        if (event.pointerType !== 'touch') setCreating(drawing)
        window.addEventListener('pointermove', onDrawMove)
        window.addEventListener('pointerup', onDrawEnd)
        window.addEventListener('pointercancel', onDrawCancel)
      },
      stopDrawing: onDrawCancel,
      // dnd-kit (pointer)
      dragStart: (event: DragStartEvent) => {
        const info = event.active.data.current as BarDragData | undefined
        const row = info ? latest.current.props.rows[info.rowIndex] : undefined
        const item = row?.items.find((candidate): candidate is StayItem => candidate.type === 'stay' && candidate.id === info?.stayId)
        if (!info || !item) return
        updateSession({ stay: item.stay, rowIndex: info.rowIndex, lane: info.lane, mode: info.mode, delta: { x: 0, y: 0 }, source: 'pointer' })
        setAnnouncement(t('dnd.start', { guest: item.stay.guest_name }))
      },
      dragMove: (event: DragMoveEvent) => {
        const current = sessionRef.current
        if (current?.source !== 'pointer') return
        const next = { ...current, delta: { x: event.delta.x, y: event.delta.y } }
        const key = snapKey(next, latest.current.props.rows, latest.current.dayWidth)
        sessionRef.current = next
        if (key === snapRef.current) return
        snapRef.current = key
        setSession(next)
      },
      dragEnd: (event: DragEndEvent) => {
        const current = sessionRef.current
        dragEndedAt.current = Date.now()
        if (current?.source !== 'pointer') return
        drop({ ...current, delta: { x: event.delta.x, y: event.delta.y } })
      },
      dragCancel: () => {
        if (sessionRef.current?.source === 'pointer') cancel()
      },
    }
  }, [t, i18n])

  // A drawing in progress stops listening to the window when the grid goes away.
  useEffect(() => handlers.stopDrawing, [handlers])

  // Keep the ghost of a keyboard move on screen.
  useEffect(() => {
    if (session?.source !== 'keyboard' || !preview || !scrollElement) return
    virtualizer.scrollToIndex(preview.rowIndex, { align: 'auto' })
    const span = preview.target ? stayColumns(preview.target.checkin, preview.target.checkout, rangeStart, days) : null
    if (!span) return
    const visible = scrollElement.clientWidth - labelWidth
    const left = span.start * dayWidth
    const right = span.end * dayWidth
    if (left < scrollElement.scrollLeft) scrollElement.scrollLeft = left
    else if (right > scrollElement.scrollLeft + visible) scrollElement.scrollLeft = right - visible
  }, [session, preview, scrollElement, virtualizer, rangeStart, days, dayWidth, labelWidth])

  useImperativeHandle(
    props.ref,
    () => ({
      focusStay(stayId: string) {
        const rowIndex = rows.findIndex((row) => row.items.some((item) => item.type === 'stay' && item.id === stayId))
        if (rowIndex === -1) return
        virtualizer.scrollToIndex(rowIndex, { align: 'center' })
        const item = rows[rowIndex].items.find((candidate) => candidate.id === stayId)
        if (scrollElement && item) scrollElement.scrollLeft = Math.max(0, (item.span.start - 1) * dayWidth)
        requestAnimationFrame(() => scrollElement?.querySelector<HTMLElement>(`[data-stay-id="${stayId}"]`)?.focus())
      },
    }),
    [rows, virtualizer, scrollElement, dayWidth],
  )

  // Constant options: a new options object would give dnd-kit new sensors on every render (every scroll frame)
  // and re-render every draggable bar through its context.
  const sensors = useSensors(useSensor(MouseSensor, MOUSE_SENSOR), useSensor(TouchSensor, TOUCH_SENSOR))
  const accessibility = useMemo(
    () => ({ announcements: SILENT, screenReaderInstructions: { draggable: t('dnd.instructions') } }),
    [t],
  )

  const todayIndex = diffDays(rangeStart, businessDate)
  const rangeLabel = formatDateRange(rangeStart, addDays(rangeStart, days - 1), lang)
  const liftedStayId = session?.source === 'keyboard' ? session.stay.id : null
  const todayLabel = t('grid.today')

  // Weekend and holiday stripes plus the line of today, behind the rows (the line runs between bars and never
  // across a guest's name). Built once per range and width, not on every scroll frame.
  const columnShading = useMemo(
    () => (
      <div aria-hidden className="pointer-events-none absolute inset-y-0" style={{ left: labelWidth, width: days * dayWidth }}>
        {dates.map((date, column) =>
          holidays.has(date) || isWeekendNight(date) ? (
            <div
              key={date}
              className={cn('absolute inset-y-0', holidays.has(date) ? 'bg-accent-soft/45' : 'bg-surface-2/80')}
              style={{ left: column * dayWidth, width: dayWidth }}
            />
          ) : null,
        )}
        {todayIndex >= 0 && todayIndex < days && (
          <div className="absolute inset-y-0 w-0.5 bg-accent/70" style={{ left: (todayIndex + 0.5) * dayWidth - 1 }} />
        )}
      </div>
    ),
    [dates, holidays, labelWidth, days, dayWidth, todayIndex],
  )

  let ghost: { row: CalendarRow; target: MoveTarget; invalid: boolean; label: string; variant: 'move' | 'create' } | null = null
  if (preview?.target && rows[preview.rowIndex]) {
    const invalid = preview.result?.kind === 'invalid'
    ghost = {
      row: rows[preview.rowIndex],
      target: preview.target,
      invalid,
      label:
        preview.result?.kind === 'invalid'
          ? invalidText(t, preview.result, lang)
          : `${targetLabel(t, lang, index, preview.target)} · ${formatDateRange(preview.target.checkin, preview.target.checkout, lang)}`,
      variant: 'move',
    }
  } else if (draft && creating && rows[creating.rowIndex]) {
    ghost = {
      row: rows[creating.rowIndex],
      target: draft,
      invalid: draftCheck?.kind === 'invalid',
      // Nights first: a one- or two-night draft is narrow and the end of the label gets cut.
      label:
        draftCheck?.kind === 'invalid'
          ? invalidText(t, draftCheck, lang)
          : `${t('date.nights', { ns: 'common', count: nightsOf(draft) })} · ${t('grid.newHere', { place: newPlaceLabel(t, lang, index, draft) })}`,
      variant: 'create',
    }
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handlers.dragStart}
      onDragMove={handlers.dragMove}
      onDragEnd={handlers.dragEnd}
      onDragCancel={handlers.dragCancel}
      accessibility={accessibility}
    >
      <p id={instructionsId} className="sr-only">
        {t('dnd.instructions')}
      </p>
      <div aria-live="assertive" aria-atomic="true" className="sr-only">
        {announcement}
      </div>
      <div
        ref={setScrollElement}
        className="relative max-h-[calc(100dvh-16.5rem)] min-h-80 overflow-auto overscroll-contain rounded-lg border border-border bg-surface shadow-xs"
      >
        <div
          role="table"
          aria-label={t('grid.label', { range: rangeLabel })}
          aria-rowcount={rows.length + 1}
          aria-colcount={days + 1}
          className="relative"
          style={{ width: contentWidth }}
        >
          <div role="rowgroup" className="sticky top-0 z-20">
            <div role="row" aria-rowindex={1} className="flex border-b border-border bg-surface" style={{ height: HEADER_HEIGHT }}>
              <div
                role="columnheader"
                className="sticky left-0 z-10 flex shrink-0 items-end border-r border-border bg-surface px-2 pb-2 sm:px-3"
                style={{ width: labelWidth }}
              >
                <span className="eyebrow">{t('grid.rooms')}</span>
              </div>
              {dates.map((date, column) => (
                <DayHeader
                  key={date}
                  date={date}
                  width={dayWidth}
                  lang={lang}
                  holiday={holidays.get(date)}
                  todayLabel={date === businessDate ? todayLabel : null}
                  showMonth={column === 0 || date.endsWith('-01')}
                />
              ))}
            </div>
          </div>

          <div
            role="rowgroup"
            className={cn('relative', creating && 'cursor-crosshair select-none')}
            style={{
              height: totalHeight(rows),
              backgroundImage: 'linear-gradient(to right, color-mix(in srgb, var(--border) 75%, transparent) 1px, transparent 1px)',
              backgroundSize: `${dayWidth}px 100%`,
              backgroundPosition: `${labelWidth}px 0`,
            }}
          >
            {columnShading}

            {virtualizer.getVirtualItems().map((item) => {
              const row = rows[item.index]
              if (!row) return null
              return (
                <GridRow
                  key={row.key}
                  row={row}
                  rowIndex={item.index}
                  top={item.start - HEADER_HEIGHT}
                  labelWidth={labelWidth}
                  dayWidth={dayWidth}
                  dates={dates}
                  lang={lang}
                  index={index}
                  availability={row.kind === 'category' ? data.availability[row.roomType.id] : undefined}
                  prices={row.kind === 'category' ? prices : null}
                  canManage={canManage}
                  businessDate={businessDate}
                  matches={matches}
                  liftedStayId={liftedStayId}
                  describedBy={instructionsId}
                  handlers={handlers}
                />
              )
            })}

            {ghost && (
              <DropGhost
                row={ghost.row}
                target={ghost.target}
                invalid={ghost.invalid}
                label={ghost.label}
                variant={ghost.variant}
                rangeStart={rangeStart}
                days={days}
                dayWidth={dayWidth}
                labelWidth={labelWidth}
              />
            )}
          </div>
        </div>
      </div>
    </DndContext>
  )
}

/**
 * Where a moved booking would land, or the booking being drawn: an outline in the target row with the same
 * half-day geometry as the bars — red, with the reason, where it cannot go.
 */
function DropGhost({
  row,
  target,
  invalid,
  label,
  variant,
  rangeStart,
  days,
  dayWidth,
  labelWidth,
}: {
  row: CalendarRow
  target: MoveTarget
  invalid: boolean
  label: string
  variant: 'move' | 'create'
  rangeStart: string
  days: number
  dayWidth: number
  labelWidth: number
}) {
  const span = stayColumns(target.checkin, target.checkout, rangeStart, days)
  if (!span) return null
  const { top, height } = barMetrics(row.kind, 0)
  const width = Math.max(12, (span.end - span.start) * dayWidth - 2)
  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none absolute z-[4] flex items-center gap-1 overflow-hidden rounded-[6px] border-2 border-dashed px-1.5 text-2xs font-bold whitespace-nowrap shadow-md',
        invalid ? 'border-danger bg-danger-soft text-danger-ink' : 'border-accent bg-accent-soft/90 text-accent-ink',
      )}
      style={{ top: row.offset + top, left: labelWidth + span.start * dayWidth + 1, width, height }}
    >
      {variant === 'create' && !invalid && width >= 28 && <Plus aria-hidden className="size-3 shrink-0" />}
      <span className="truncate">{label}</span>
    </div>
  )
}

/** A day of the header (memoized: the grid re-renders on every scroll frame, the days do not change). */
const DayHeader = memo(function DayHeader({
  date,
  width,
  lang,
  holiday,
  todayLabel,
  showMonth,
}: {
  date: string
  width: number
  lang: Lang
  holiday: string | undefined
  /** "Hoy" on the business date, `null` on the other days. */
  todayLabel: string | null
  showMonth: boolean
}) {
  const isToday = todayLabel !== null
  const label = [formatDate(date, 'EEE d MMM', lang), holiday, todayLabel].filter(Boolean).join(' · ')
  return (
    <div
      role="columnheader"
      aria-label={label}
      title={holiday}
      className={cn(
        'relative flex shrink-0 flex-col items-center justify-end pb-1.5',
        isWeekendNight(date) && 'bg-surface-2/80',
        holiday && 'bg-accent-soft/45',
        isToday && 'shadow-[inset_0_3px_0_var(--accent)]',
      )}
      style={{ width }}
    >
      {showMonth && (
        <span aria-hidden className="absolute top-1 left-1.5 text-2xs leading-4 font-bold text-muted uppercase">
          {formatDate(date, 'MMM', lang)}
        </span>
      )}
      {holiday && <span aria-hidden className="absolute top-2 right-1.5 size-1.5 rounded-full bg-accent" />}
      <span aria-hidden className={cn('eyebrow', (holiday || isToday) && '!text-accent-ink')}>
        {formatDate(date, 'EEE', lang)}
      </span>
      <span aria-hidden className={cn('num text-base leading-5 font-bold tracking-[-0.02em]', isToday ? 'text-accent-ink' : 'text-fg')}>
        {formatDate(date, 'd', lang)}
      </span>
    </div>
  )
})
