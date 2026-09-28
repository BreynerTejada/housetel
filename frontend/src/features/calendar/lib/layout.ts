import type { CalBed, CalBlock, CalendarData, CalRoom, CalRoomType, CalStay, StayStatus } from '../api'
import { diffDays } from './dates'

// ---- Geometry ---------------------------------------------------------------------------------------
//
// Columns are days of the range (column i = the day `rangeStart + i`). A stay occupies its nights, so its bar
// runs from the middle of the arrival day (check-in in the afternoon) to the middle of the departure day
// (check-out in the morning): a departure and an arrival on the same day meet in that day's column without
// overlapping. Everything that takes nights (stays and blocks) uses the same rule. Units are columns.

export interface Span {
  start: number
  end: number
  /** The bar continues before the first day / after the last day of the range. */
  clippedStart: boolean
  clippedEnd: boolean
}

/** Position of the nights `[checkin, checkout)` in a range of `days` columns from `rangeStart`; `null` if outside. */
export function stayColumns(checkin: string, checkout: string, rangeStart: string, days: number): Span | null {
  const rawStart = diffDays(rangeStart, checkin) + 0.5
  const rawEnd = diffDays(rangeStart, checkout) + 0.5
  if (rawEnd <= rawStart || rawEnd <= 0 || rawStart >= days) return null
  return {
    start: Math.max(0, rawStart),
    end: Math.min(days, rawEnd),
    clippedStart: rawStart < 0,
    clippedEnd: rawEnd > days,
  }
}

/**
 * Greedy interval partitioning: each item takes the first lane that is free when it starts (an item that
 * starts where another ends shares its lane). `laneOf` follows the input order.
 */
export function assignLanes(items: readonly { start: number; end: number }[]): { lanes: number; laneOf: number[] } {
  const order = items.map((_, index) => index).sort((a, b) => items[a].start - items[b].start || items[a].end - items[b].end)
  const laneEnds: number[] = []
  const laneOf: number[] = new Array(items.length)
  for (const index of order) {
    const item = items[index]
    let lane = laneEnds.findIndex((end) => end <= item.start)
    if (lane === -1) {
      lane = laneEnds.length
      laneEnds.push(item.end)
    } else {
      laneEnds[lane] = item.end
    }
    laneOf[index] = lane
  }
  return { lanes: laneEnds.length, laneOf }
}

// ---- Rows -------------------------------------------------------------------------------------------

export type RowKind = 'category' | 'unassigned' | 'room' | 'dorm' | 'bed'

/** Heights in px. Room and bed rows grow one lane per overlapping bar (overbooked rooms, history). */
export const ROW_HEIGHT = {
  category: 52,
  unassignedLane: 32,
  unassignedEmpty: 28,
  roomLane: 40,
  dormLane: 30,
  bedLane: 32,
} as const

/** Narrowest day that still shows a guest's name, by how many days are on screen. */
const MIN_DAY_WIDTH: readonly [maxDays: number, px: number][] = [
  [7, 96],
  [14, 60],
  [Infinity, 42],
]
const MAX_DAY_WIDTH = 200

/**
 * Width of a day column: the days share what is left after the room column, but never get narrower than
 * the minimum for the span (the grid then scrolls sideways, e.g. on a phone) nor wider than 200 px.
 */
export function dayWidthFor(containerWidth: number, days: number, labelWidth: number): number {
  const minimum = MIN_DAY_WIDTH.find(([maxDays]) => days <= maxDays)?.[1] ?? 42
  const share = days > 0 ? Math.floor((containerWidth - labelWidth) / days) : minimum
  return Math.min(MAX_DAY_WIDTH, Math.max(minimum, share))
}

/** Vertical box of a bar inside its row: one lane per overlapping bar, inset so stacked bars do not touch. */
export function barMetrics(kind: RowKind, lane: number): { top: number; height: number } {
  const [laneHeight, inset] =
    kind === 'room'
      ? [ROW_HEIGHT.roomLane, 5]
      : kind === 'dorm'
        ? [ROW_HEIGHT.dormLane, 4]
        : kind === 'bed'
          ? [ROW_HEIGHT.bedLane, 4]
          : [ROW_HEIGHT.unassignedLane, 4]
  return { top: lane * laneHeight + inset, height: laneHeight - 2 * inset }
}

export interface StayItem {
  type: 'stay'
  id: string
  stay: CalStay
  span: Span
  lane: number
  /** The room belongs to another category than the one booked. */
  upgrade: boolean
}

export interface BlockItem {
  type: 'block'
  id: string
  block: CalBlock
  span: Span
  lane: number
  /** A whole-room dorm block drawn on each of its beds. */
  inherited: boolean
}

export type RowItem = StayItem | BlockItem

export interface CalendarRow {
  /** `rt:<roomTypeId>` · `un:<roomTypeId>:<lane>` · `room:<roomId>` · `dorm:<roomId>` · `bed:<bedId>` */
  key: string
  kind: RowKind
  roomType: CalRoomType
  room: CalRoom | null
  bed: CalBed | null
  items: RowItem[]
  /** Lanes inside the row. */
  lanes: number
  height: number
  offset: number
  /** Category rows: rooms hidden. Unassigned rows: the group is folded into per-night counts. */
  collapsed?: boolean
  /** Unassigned rows: first row of the group (carries the label) and how many stays the group has. */
  first?: boolean
  unassignedCount?: number
  /** Folded unassigned group: stays per night of the range. */
  counts?: number[]
  /** Dorm rooms: beds neither taken by a stay nor blocked, per night of the range. */
  free?: number[]
}

export interface BuildRowsOptions {
  rangeStart: string
  days: number
  /** `rt:<id>` folds a category; `un:<id>` folds its unassigned group. */
  collapsed?: ReadonlySet<string>
  /** Categories to show (`null` or empty = all). */
  categories?: ReadonlySet<string> | null
  /** Stay statuses to show (`null` = all). Blocks always show. */
  statuses?: ReadonlySet<StayStatus> | null
}

const NO_KEYS: ReadonlySet<string> = new Set()

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key)
  if (list) list.push(value)
  else map.set(key, [value])
}

function byStart(a: RowItem, b: RowItem): number {
  return (
    a.span.start - b.span.start ||
    a.span.end - b.span.end ||
    (a.type === b.type ? 0 : a.type === 'stay' ? -1 : 1) ||
    a.id.localeCompare(b.id)
  )
}

/** Sorts the items of one row and stacks the overlapping ones in lanes. */
function laneItems(items: RowItem[]): { items: RowItem[]; lanes: number } {
  const sorted = [...items].sort(byStart)
  const { lanes, laneOf } = assignLanes(sorted.map((item) => item.span))
  return { items: sorted.map((item, index) => ({ ...item, lane: laneOf[index] })), lanes }
}

/**
 * The calendar as a flat list of rows (what the virtualizer renders): per category a summary row
 * (availability and price), its unassigned stays in lanes, and its rooms — a dorm room followed by its beds.
 */
export function buildRows(data: CalendarData, options: BuildRowsOptions): CalendarRow[] {
  const { rangeStart, days } = options
  const collapsed = options.collapsed ?? NO_KEYS
  const categories = options.categories && options.categories.size > 0 ? options.categories : null
  const statuses = options.statuses ?? null

  const roomTypeOfRoom = new Map<string, CalRoomType>()
  const bedIds = new Set<string>()
  for (const roomType of data.room_types) {
    for (const room of roomType.rooms) {
      roomTypeOfRoom.set(room.id, roomType)
      for (const bed of room.beds) bedIds.add(bed.id)
    }
  }

  const roomStays = new Map<string, RowItem[]>()
  const bedStays = new Map<string, RowItem[]>()
  const unassigned = new Map<string, StayItem[]>()
  for (const stay of data.stays) {
    if (statuses && !statuses.has(stay.status)) continue
    const span = stayColumns(stay.checkin, stay.checkout, rangeStart, days)
    if (!span) continue
    const roomType = stay.room_id ? roomTypeOfRoom.get(stay.room_id) : undefined
    const item: StayItem = {
      type: 'stay',
      id: stay.id,
      stay,
      span,
      lane: 0,
      upgrade: Boolean(roomType && roomType.id !== stay.room_type_id),
    }
    if (stay.bed_id && bedIds.has(stay.bed_id)) push(bedStays, stay.bed_id, item)
    else if (roomType && stay.room_id) push(roomStays, stay.room_id, item)
    else push(unassigned, stay.room_type_id, { ...item, upgrade: false })
  }

  const roomBlocks = new Map<string, CalBlock[]>()
  const bedBlocks = new Map<string, CalBlock[]>()
  for (const block of data.blocks) {
    if (block.bed_id) push(bedBlocks, block.bed_id, block)
    else push(roomBlocks, block.room_id, block)
  }

  // Occupancy of beds counts every stay the calendar returns, whatever the status filter shows.
  const nightsOfBed = new Map<string, [number, number][]>()
  for (const stay of data.stays) {
    if (stay.bed_id) push(nightsOfBed, stay.bed_id, [diffDays(rangeStart, stay.checkin), diffDays(rangeStart, stay.checkout)])
  }
  const covers = (ranges: [number, number][] | undefined, night: number) =>
    (ranges ?? []).some(([from, to]) => from <= night && night < to)
  const blockNights = (blocks: CalBlock[] | undefined): [number, number][] =>
    (blocks ?? []).map((block) => [diffDays(rangeStart, block.start), diffDays(rangeStart, block.end)])
  const freeBeds = (room: CalRoom): number[] => {
    const wholeRoom = blockNights(roomBlocks.get(room.id))
    return Array.from({ length: days }, (_, night) =>
      covers(wholeRoom, night)
        ? 0
        : room.beds.filter((bed) => !covers(nightsOfBed.get(bed.id), night) && !covers(blockNights(bedBlocks.get(bed.id)), night))
            .length,
    )
  }

  const blockItems = (blocks: CalBlock[] | undefined, inherited: boolean): RowItem[] =>
    (blocks ?? []).flatMap((block) => {
      const span = stayColumns(block.start, block.end, rangeStart, days)
      return span ? [{ type: 'block' as const, id: block.id, block, span, lane: 0, inherited }] : []
    })

  const rows: CalendarRow[] = []
  let offset = 0
  const add = (row: Omit<CalendarRow, 'offset'>) => {
    rows.push({ ...row, offset })
    offset += row.height
  }

  for (const roomType of data.room_types) {
    if (categories && !categories.has(roomType.id)) continue
    const folded = collapsed.has(`rt:${roomType.id}`)
    add({ key: `rt:${roomType.id}`, kind: 'category', roomType, room: null, bed: null, items: [], lanes: 0, height: ROW_HEIGHT.category, collapsed: folded })
    if (folded) continue

    const pending = unassigned.get(roomType.id) ?? []
    const base = { kind: 'unassigned' as const, roomType, room: null, bed: null, unassignedCount: pending.length }
    if (collapsed.has(`un:${roomType.id}`)) {
      const counts = Array.from({ length: days }, (_, night) =>
        pending.filter(({ stay }) => diffDays(rangeStart, stay.checkin) <= night && night < diffDays(rangeStart, stay.checkout)).length,
      )
      add({ ...base, key: `un:${roomType.id}:0`, items: [], lanes: 1, height: ROW_HEIGHT.unassignedLane, first: true, collapsed: true, counts })
    } else if (pending.length === 0) {
      add({ ...base, key: `un:${roomType.id}:0`, items: [], lanes: 1, height: ROW_HEIGHT.unassignedEmpty, first: true })
    } else {
      const sorted = [...pending].sort(byStart)
      const { lanes, laneOf } = assignLanes(sorted.map((item) => item.span))
      for (let lane = 0; lane < lanes; lane += 1) {
        add({
          ...base,
          key: `un:${roomType.id}:${lane}`,
          items: sorted.filter((_, index) => laneOf[index] === lane),
          lanes: 1,
          height: ROW_HEIGHT.unassignedLane,
          first: lane === 0,
        })
      }
    }

    for (const room of roomType.rooms) {
      if (roomType.kind === 'dorm' || room.beds.length > 0) {
        const own = laneItems([...(roomStays.get(room.id) ?? []), ...blockItems(roomBlocks.get(room.id), false)])
        add({
          key: `dorm:${room.id}`,
          kind: 'dorm',
          roomType,
          room,
          bed: null,
          ...own,
          height: Math.max(1, own.lanes) * ROW_HEIGHT.dormLane,
          free: freeBeds(room),
        })
        for (const bed of room.beds) {
          const bedRow = laneItems([
            ...(bedStays.get(bed.id) ?? []),
            ...blockItems(bedBlocks.get(bed.id), false),
            ...blockItems(roomBlocks.get(room.id), true),
          ])
          add({ key: `bed:${bed.id}`, kind: 'bed', roomType, room, bed, ...bedRow, height: Math.max(1, bedRow.lanes) * ROW_HEIGHT.bedLane })
        }
      } else {
        const own = laneItems([...(roomStays.get(room.id) ?? []), ...blockItems(roomBlocks.get(room.id), false)])
        add({ key: `room:${room.id}`, kind: 'room', roomType, room, bed: null, ...own, height: Math.max(1, own.lanes) * ROW_HEIGHT.roomLane })
      }
    }
  }
  return rows
}

/** An unassigned group needing more lanes than this starts folded into per-night counts. */
export const MAX_OPEN_UNASSIGNED_LANES = 4

/**
 * Groups folded until the user says otherwise: the unassigned stays of a category that would stack in more
 * than `MAX_OPEN_UNASSIGNED_LANES` lanes over the range (a busy future of bookings still waiting for a room
 * would otherwise push every room far below). Counts every stay of the range, whatever the filters show,
 * so filtering never folds or unfolds a group.
 */
export function defaultCollapsed(data: CalendarData, options: Pick<BuildRowsOptions, 'rangeStart' | 'days'>): Set<string> {
  const spans = new Map<string, Span[]>()
  for (const stay of data.stays) {
    if (stay.room_id) continue
    const span = stayColumns(stay.checkin, stay.checkout, options.rangeStart, options.days)
    if (span) push(spans, stay.room_type_id, span)
  }
  const folded = new Set<string>()
  for (const [roomTypeId, list] of spans) {
    if (assignLanes(list).lanes > MAX_OPEN_UNASSIGNED_LANES) folded.add(`un:${roomTypeId}`)
  }
  return folded
}

/** Folded keys: what the user folded (`true`) or unfolded (`false`) wins; the defaults cover the rest. */
export function resolveCollapsed(defaults: ReadonlySet<string>, overrides: Readonly<Record<string, boolean>>): Set<string> {
  const folded = new Set([...defaults].filter((key) => overrides[key] !== false))
  for (const [key, isFolded] of Object.entries(overrides)) if (isFolded) folded.add(key)
  return folded
}

export function totalHeight(rows: readonly CalendarRow[]): number {
  const last = rows.at(-1)
  return last ? last.offset + last.height : 0
}

/** Index of the row under the vertical position `y` (0 = top of the first row); `-1` outside the rows. */
export function rowIndexAt(rows: readonly CalendarRow[], y: number): number {
  if (y < 0 || y >= totalHeight(rows)) return -1
  let low = 0
  let high = rows.length - 1
  while (low < high) {
    const mid = Math.ceil((low + high) / 2)
    if (rows[mid].offset <= y) low = mid
    else high = mid - 1
  }
  return low
}
