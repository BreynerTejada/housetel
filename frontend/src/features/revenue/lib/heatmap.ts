import type { CalendarCell, CalendarResponse, RatePlanRef, RoomTypeRef } from '../api'
import { isWeekendNight } from './dates'

export interface HeatColumn {
  date: string
  /** Friday or Saturday night. */
  weekend: boolean
  /** Name of the Colombian holiday of that night, if any. */
  holiday: string | null
  /** The business date of the property. */
  today: boolean
  /** First column or first night of a month: the header names the month. */
  monthStart: boolean
}

export interface HeatCell {
  date: string
  /** `null` when the night has no recommendation (or its decided one is hidden). */
  cell: CalendarCell | null
}

export interface HeatRow {
  key: string
  roomType: RoomTypeRef
  ratePlan: RatePlanRef
  cells: HeatCell[]
}

export interface HeatmapModel {
  columns: HeatColumn[]
  rows: HeatRow[]
  /** Pending recommendations on screen, row by row: what "select all" takes. */
  pendingIds: string[]
  /** More than one base plan: rows must name their plan. */
  manyPlans: boolean
}

/** Rows × nights of the recommendations calendar, ready to draw. */
export function buildHeatmap(calendar: CalendarResponse, { showDecided }: { showDecided: boolean }): HeatmapModel {
  const holidays = new Map(calendar.holidays.map((holiday) => [holiday.date, holiday.name]))
  const columns = calendar.dates.map((date, index) => ({
    date,
    weekend: isWeekendNight(date),
    holiday: holidays.get(date) ?? null,
    today: date === calendar.business_date,
    monthStart: index === 0 || date.endsWith('-01'),
  }))
  const rows = calendar.rows.map((row) => ({
    key: `${row.room_type.id}:${row.rate_plan.id}`,
    roomType: row.room_type,
    ratePlan: row.rate_plan,
    cells: calendar.dates.map((date) => {
      const found = row.cells[date] ?? null
      return { date, cell: found && (showDecided || found.status === 'pending') ? found : null }
    }),
  }))
  return {
    columns,
    rows,
    pendingIds: rows.flatMap(rowPendingIds),
    manyPlans: new Set(calendar.rows.map((row) => row.rate_plan.id)).size > 1,
  }
}

export function rowPendingIds(row: HeatRow): string[] {
  return row.cells.flatMap((item) => (item.cell?.status === 'pending' ? [item.cell.id] : []))
}

export function columnPendingIds(model: HeatmapModel, date: string): string[] {
  return model.rows.flatMap((row) => {
    const found = row.cells.find((item) => item.date === date)?.cell
    return found?.status === 'pending' ? [found.id] : []
  })
}

/** Adds `ids` to the selection, or removes them when every one is already selected. */
export function toggleIds(selected: ReadonlySet<string>, ids: string[]): Set<string> {
  const next = new Set(selected)
  const allIn = ids.length > 0 && ids.every((id) => next.has(id))
  for (const id of ids) {
    if (allIn) next.delete(id)
    else next.add(id)
  }
  return next
}

/** Keeps only what is still pending on screen (a new range, a decision, a new run). */
export function pruneSelection(selected: ReadonlySet<string>, model: HeatmapModel): Set<string> {
  const pending = new Set(model.pendingIds)
  return new Set([...selected].filter((id) => pending.has(id)))
}
