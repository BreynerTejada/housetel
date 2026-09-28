import type { CalBed, CalBlock, CalendarData, CalRoomType, CalStay, I18nText } from '../api'
import { addDays } from './dates'
import { ROW_HEIGHT, rowIndexAt, type CalendarRow } from './layout'

// Translating what the user does on the grid (drag a bar, stretch its edge, pick a room in the "Move"
// dialog) into the bookings API calls that make it happen, and validating it against what the grid
// already shows. Pure: the UI and the tests share it.

/** Where a stay is, or would be. `roomTypeId` is the booked category. */
export interface Placement {
  roomTypeId: string
  roomId: string | null
  bedId: string | null
  checkin: string
  checkout: string
}

/** Where the user put the stay: the category of the row it landed on, its room/bed and the new nights. */
export interface MoveTarget {
  roomTypeId: string
  roomId: string | null
  /** `null` with a dorm `roomId`: any free bed of that room. */
  bedId: string | null
  checkin: string
  checkout: string
}

export interface ModifyBody {
  checkin?: string
  checkout?: string
  room_type_id?: string
  reprice: boolean
}

export interface AssignBody {
  room_id: string
  bed_id: string | null
  force?: boolean
}

export type Step = { op: 'modify'; body: ModifyBody } | { op: 'assign'; body: AssignBody } | { op: 'unassign' }

export interface PlanOption {
  steps: Step[]
  /** The stay once the steps ran (optimistic update). */
  next: Placement
}

export interface ChangePlan {
  stayId: string
  from: Placement
  /**
   * What needs the user's OK before running: `none` (a room move: same price), `dates` (the price may
   * change) or `category` (choose between repricing in the new category and an upgrade at the same price).
   */
  confirm: 'none' | 'dates' | 'category'
  /** `null` when the only way is the upgrade (an in-house guest keeps the booked category). */
  primary: PlanOption | null
  /** Category changes into a room: take it as an upgrade (booked category and price unchanged). */
  upgrade: PlanOption | null
}

export type InvalidReason =
  | 'finished'
  | 'kind_mismatch'
  | 'min_one_night'
  | 'in_house_arrival'
  | 'in_house_departure'
  | 'in_house_unassign'
  | 'past_arrival'
  | 'occupied'
  | 'blocked'
  | 'no_free_bed'
  | 'no_units'

export type Conflict =
  | { type: 'stay'; code: string; guest: string }
  | { type: 'block'; kind: string; reason: string }
  /** The category has no sellable unit left on `date` (what the calendar's availability row shows). */
  | { type: 'units'; category: I18nText; date: string }

export type PlanResult =
  | { kind: 'noop' }
  | { kind: 'invalid'; reason: InvalidReason; conflict?: Conflict }
  | { kind: 'plan'; plan: ChangePlan }

// ---- Geometry of a drag -----------------------------------------------------------------------------

/** Whole days for a horizontal distance, rounded symmetrically (half a day back is one day back). */
export function roundDays(px: number, dayWidth: number): number {
  const days = Math.round(Math.abs(px) / dayWidth)
  return px < 0 ? -days || 0 : days
}

function laneCenter(row: CalendarRow, lane: number): number {
  switch (row.kind) {
    case 'room':
      return lane * ROW_HEIGHT.roomLane + ROW_HEIGHT.roomLane / 2
    case 'bed':
      return lane * ROW_HEIGHT.bedLane + ROW_HEIGHT.bedLane / 2
    case 'dorm':
      return lane * ROW_HEIGHT.dormLane + ROW_HEIGHT.dormLane / 2
    default:
      return row.height / 2
  }
}

/**
 * Where a dragged bar lands: the row under the center of its lane once moved by `delta` (px, already
 * adjusted for scrolling) and the whole days it moved. `null` when it is dropped outside the rows.
 */
export function resolveMove(
  rows: readonly CalendarRow[],
  dayWidth: number,
  originRowIndex: number,
  originLane: number,
  delta: { x: number; y: number },
): { rowIndex: number; dayDelta: number } | null {
  const origin = rows[originRowIndex]
  if (!origin) return null
  const rowIndex = rowIndexAt(rows, origin.offset + laneCenter(origin, originLane) + delta.y)
  if (rowIndex === -1) return null
  return { rowIndex, dayDelta: roundDays(delta.x, dayWidth) }
}

export type DragMode = 'move' | 'resize'

/**
 * Keyboard moves (the bar was picked up with M): ←/→ move one whole day; ↑/↓ jump to the next row that can
 * take a stay (category rows are skipped), keeping the days already moved. Returns the new drag delta —
 * the same px delta a pointer drag produces, so `resolveMove` lands it — or `null` when the key does not
 * move anything (edge of the grid, another key, or ↑/↓ while stretching the departure).
 */
export function keyboardDelta(
  rows: readonly CalendarRow[],
  dayWidth: number,
  origin: { rowIndex: number; lane: number },
  delta: { x: number; y: number },
  key: string,
  mode: DragMode = 'move',
): { x: number; y: number } | null {
  if (key === 'ArrowRight') return { x: delta.x + dayWidth, y: delta.y }
  if (key === 'ArrowLeft') return { x: delta.x - dayWidth, y: delta.y }
  if (mode === 'resize' || (key !== 'ArrowDown' && key !== 'ArrowUp')) return null

  const from = rows[origin.rowIndex]
  const landed = resolveMove(rows, dayWidth, origin.rowIndex, origin.lane, delta)
  if (!from || !landed) return null
  const step = key === 'ArrowDown' ? 1 : -1
  for (let index = landed.rowIndex + step; index >= 0 && index < rows.length; index += step) {
    const row = rows[index]
    if (!targetForRow(row)) continue
    const y = row.offset + laneCenter(row, 0) - (from.offset + laneCenter(from, origin.lane))
    return { x: delta.x, y }
  }
  return null
}

/** The place a row stands for; category (summary) rows are not drop targets. */
export function targetForRow(row: CalendarRow): Pick<MoveTarget, 'roomTypeId' | 'roomId' | 'bedId'> | null {
  switch (row.kind) {
    case 'unassigned':
      return { roomTypeId: row.roomType.id, roomId: null, bedId: null }
    case 'room':
    case 'dorm':
      return { roomTypeId: row.roomType.id, roomId: row.room?.id ?? null, bedId: null }
    case 'bed':
      return { roomTypeId: row.roomType.id, roomId: row.room?.id ?? null, bedId: row.bed?.id ?? null }
    default:
      return null
  }
}

/** Stretching the right edge by `nights`: at least one night, and an in-house guest cannot leave before today. */
export function resizeTarget(stay: CalStay, nights: number, businessDate: string): MoveTarget {
  let min = addDays(stay.checkin, 1)
  if (stay.status === 'checked_in' && businessDate > min) min = businessDate
  const wanted = addDays(stay.checkout, nights)
  return {
    roomTypeId: stay.room_type_id,
    roomId: stay.room_id,
    bedId: stay.bed_id,
    checkin: stay.checkin,
    checkout: wanted < min ? min : wanted,
  }
}

// ---- What the grid knows about occupancy ------------------------------------------------------------

const ACTIVE = new Set(['tentative', 'confirmed', 'checked_in'])

export interface PlanContext {
  businessDate: string
  roomTypes: Map<string, CalRoomType>
  roomTypeOfRoom: Map<string, CalRoomType>
  bedsOfRoom: Map<string, CalBed[]>
  roomStays: Map<string, CalStay[]>
  bedStays: Map<string, CalStay[]>
  roomBlocks: Map<string, CalBlock[]>
  bedBlocks: Map<string, CalBlock[]>
  /** Sellable units per category and night, for the nights the calendar loaded (others are unknown). */
  availability: CalendarData['availability']
}

function push<V>(map: Map<string, V[]>, key: string, value: V) {
  const list = map.get(key)
  if (list) list.push(value)
  else map.set(key, [value])
}

export function createPlanContext(data: CalendarData, businessDate: string): PlanContext {
  const ctx: PlanContext = {
    businessDate,
    roomTypes: new Map(data.room_types.map((roomType) => [roomType.id, roomType])),
    roomTypeOfRoom: new Map(),
    bedsOfRoom: new Map(),
    roomStays: new Map(),
    bedStays: new Map(),
    roomBlocks: new Map(),
    bedBlocks: new Map(),
    availability: data.availability ?? {},
  }
  for (const roomType of data.room_types) {
    for (const room of roomType.rooms) {
      ctx.roomTypeOfRoom.set(room.id, roomType)
      ctx.bedsOfRoom.set(room.id, room.beds)
    }
  }
  for (const stay of data.stays) {
    if (!ACTIVE.has(stay.status)) continue // a finished stay no longer holds its room
    if (stay.bed_id) push(ctx.bedStays, stay.bed_id, stay)
    else if (stay.room_id) push(ctx.roomStays, stay.room_id, stay)
  }
  for (const block of data.blocks) {
    if (block.bed_id) push(ctx.bedBlocks, block.bed_id, block)
    else push(ctx.roomBlocks, block.room_id, block)
  }
  return ctx
}

function overlaps(aIn: string, aOut: string, bIn: string, bOut: string): boolean {
  return aIn < bOut && bIn < aOut
}

/**
 * First stay or block that would share the room (or bed) on those nights, ignoring the stay `stayId` itself
 * (pass `null` for a new booking). A private room also clashes with anything on its beds, and a bed with a
 * whole-room block.
 */
export function unitConflict(
  ctx: PlanContext,
  stayId: string | null,
  roomId: string,
  bedId: string | null,
  checkin: string,
  checkout: string,
): Conflict | null {
  const stays = (bedId ? ctx.bedStays.get(bedId) : ctx.roomStays.get(roomId)) ?? []
  for (const other of stays) {
    if (other.id !== stayId && overlaps(checkin, checkout, other.checkin, other.checkout)) {
      return { type: 'stay', code: other.code, guest: other.guest_name }
    }
  }
  const blocks = [...((bedId && ctx.bedBlocks.get(bedId)) || []), ...(ctx.roomBlocks.get(roomId) ?? [])]
  for (const block of blocks) {
    if (overlaps(checkin, checkout, block.start, block.end)) return { type: 'block', kind: block.kind, reason: block.reason }
  }
  return null
}

export function isDorm(ctx: PlanContext, roomId: string): boolean {
  return (ctx.bedsOfRoom.get(roomId)?.length ?? 0) > 0 || ctx.roomTypeOfRoom.get(roomId)?.kind === 'dorm'
}

/** Beds of a dorm room free on every night of `[checkin, checkout)` (ignoring `stayId`). */
export function freeBeds(ctx: PlanContext, stayId: string | null, roomId: string, checkin: string, checkout: string): CalBed[] {
  return (ctx.bedsOfRoom.get(roomId) ?? []).filter((bed) => !unitConflict(ctx, stayId, roomId, bed.id, checkin, checkout))
}

/** The category whose inventory a stay uses: the one of its room when it has one (an upgrade takes a unit there), else the booked one. */
export function inventoryCategory(ctx: PlanContext, roomId: string | null, bookedRoomTypeId: string): string {
  return (roomId && ctx.roomTypeOfRoom.get(roomId)?.id) || bookedRoomTypeId
}

/**
 * First night of `[checkin, checkout)` on which the category has fewer than `units` sellable units, as far as
 * the calendar knows (nights it did not load are skipped: the server checks them). Nights in `held` are
 * skipped too: the stay already holds a unit of this category on them.
 */
export function unitsShortfall(
  ctx: PlanContext,
  roomTypeId: string,
  checkin: string,
  checkout: string,
  units = 1,
  held?: { checkin: string; checkout: string },
): Conflict | null {
  const nights = ctx.availability[roomTypeId]
  const roomType = ctx.roomTypes.get(roomTypeId)
  if (!nights || !roomType) return null
  for (let night = checkin; night < checkout; night = addDays(night, 1)) {
    if (held && held.checkin <= night && night < held.checkout) continue
    const available = nights[night]
    if (available !== undefined && available < units) return { type: 'units', category: roomType.name, date: night }
  }
  return null
}

// ---- Planning -----------------------------------------------------------------------------------------

export function placementOf(stay: CalStay): Placement {
  return { roomTypeId: stay.room_type_id, roomId: stay.room_id, bedId: stay.bed_id, checkin: stay.checkin, checkout: stay.checkout }
}

function invalid(reason: InvalidReason, conflict?: Conflict): PlanResult {
  return conflict ? { kind: 'invalid', reason, conflict } : { kind: 'invalid', reason }
}

/**
 * The API calls that put `stay` at `target`, or why it cannot go there. Rules:
 * - finished stays do not move; dorm beds and private rooms never mix;
 * - an in-house guest keeps the arrival date, keeps a room and cannot leave before the business date;
 * - a new arrival date cannot be in the past (business date);
 * - the target room/bed must be free and unblocked on the new nights (what the grid shows; the server
 *   checks again);
 * - new dates keep the agreed price of nights that stay (`reprice: false`) and quote the new ones;
 * - another category: reprice everything in it (`modify` + `assign`) or take the room as an upgrade at the
 *   same price (`assign` with `force`).
 */
export function planChange(stay: CalStay, target: MoveTarget, ctx: PlanContext): PlanResult {
  if (stay.status === 'checked_out') return invalid('finished')

  const booked = ctx.roomTypes.get(stay.room_type_id)
  const landing = ctx.roomTypes.get(target.roomTypeId)
  if (booked && landing && booked.kind !== landing.kind) return invalid('kind_mismatch')
  if (target.checkout <= target.checkin) return invalid('min_one_night')

  const inHouse = stay.status === 'checked_in'
  const arrivalChanged = target.checkin !== stay.checkin
  const departureChanged = target.checkout !== stay.checkout
  const datesChanged = arrivalChanged || departureChanged
  if (inHouse && arrivalChanged) return invalid('in_house_arrival')
  if (inHouse && target.checkout < ctx.businessDate) return invalid('in_house_departure')
  if (inHouse && target.roomId === null) return invalid('in_house_unassign')
  if (!inHouse && arrivalChanged && target.checkin < ctx.businessDate) return invalid('past_arrival')

  const anyBed = target.roomId !== null && target.bedId === null && isDorm(ctx, target.roomId)
  const sameUnit =
    target.roomId === stay.room_id && (target.bedId === stay.bed_id || (anyBed && stay.room_id !== null))
  // Staying in its own room never changes the category (an upgrade keeps its booked category).
  const categoryChanged = target.roomTypeId !== stay.room_type_id && !(target.roomId !== null && sameUnit)
  if (sameUnit && !datesChanged && !categoryChanged) return { kind: 'noop' }

  if (target.roomId !== null) {
    if (anyBed && !sameUnit) {
      if (freeBeds(ctx, stay.id, target.roomId, target.checkin, target.checkout).length === 0) return invalid('no_free_bed')
    } else {
      const conflict = unitConflict(ctx, stay.id, target.roomId, sameUnit ? stay.bed_id : target.bedId, target.checkin, target.checkout)
      if (conflict) return invalid(conflict.type === 'stay' ? 'occupied' : 'blocked', conflict)
    }
  }

  // Inventory: the nights the stay would newly take in the category it ends up counting in need a sellable
  // unit there (the server refuses them otherwise, even with the room itself free: unassigned bookings of
  // the category hold units too). Same category → only the added nights; another category → every night.
  const fromCategory = inventoryCategory(ctx, stay.room_id, stay.room_type_id)
  const toCategory = inventoryCategory(ctx, sameUnit ? stay.room_id : target.roomId, target.roomTypeId)
  const held = toCategory === fromCategory ? { checkin: stay.checkin, checkout: stay.checkout } : undefined
  const shortfall = unitsShortfall(ctx, toCategory, target.checkin, target.checkout, 1, held)
  if (shortfall) return invalid('no_units', shortfall)

  const dates: Pick<ModifyBody, 'checkin' | 'checkout'> = {}
  if (arrivalChanged) dates.checkin = target.checkin
  if (departureChanged) dates.checkout = target.checkout
  const datesStep: Step[] = datesChanged ? [{ op: 'modify', body: { ...dates, reprice: false } }] : []
  const from = placementOf(stay)
  const placed = (roomTypeId: string): Placement => ({
    roomTypeId,
    roomId: sameUnit ? stay.room_id : target.roomId,
    bedId: sameUnit ? stay.bed_id : target.bedId,
    checkin: target.checkin,
    checkout: target.checkout,
  })

  if (!categoryChanged) {
    let steps: Step[] = datesStep
    if (!sameUnit) {
      steps =
        target.roomId === null
          ? [{ op: 'unassign' }, ...datesStep]
          : [...datesStep, { op: 'assign', body: { room_id: target.roomId, bed_id: target.bedId } }]
    }
    const plan: ChangePlan = {
      stayId: stay.id,
      from,
      confirm: datesChanged ? 'dates' : 'none',
      primary: { steps, next: placed(stay.room_type_id) },
      upgrade: null,
    }
    return { kind: 'plan', plan }
  }

  const reprice: Step = { op: 'modify', body: { room_type_id: target.roomTypeId, ...dates, reprice: true } }
  const assign = (force: boolean): Step[] =>
    target.roomId === null ? [] : [{ op: 'assign', body: { room_id: target.roomId, bed_id: target.bedId, ...(force ? { force } : {}) } }]
  const plan: ChangePlan = {
    stayId: stay.id,
    from,
    confirm: 'category',
    primary: inHouse ? null : { steps: [reprice, ...assign(false)], next: placed(target.roomTypeId) },
    upgrade: target.roomId === null ? null : { steps: [...datesStep, ...assign(true)], next: placed(stay.room_type_id) },
  }
  return { kind: 'plan', plan }
}

export type CreateCheck = { kind: 'ok' } | Extract<PlanResult, { kind: 'invalid' }>

/**
 * Whether a new booking fits where it was drawn (dragging over empty days): at least one night, arriving
 * today or later, the room — or bed, or one bed of a dorm room — free and unblocked on those nights, and a
 * sellable unit of the category left each night. The server checks everything again when it is created.
 */
export function checkCreate(target: MoveTarget, ctx: PlanContext, units = 1): CreateCheck {
  if (target.checkout <= target.checkin) return { kind: 'invalid', reason: 'min_one_night' }
  if (target.checkin < ctx.businessDate) return { kind: 'invalid', reason: 'past_arrival' }
  if (target.roomId !== null) {
    if (target.bedId === null && isDorm(ctx, target.roomId)) {
      if (freeBeds(ctx, null, target.roomId, target.checkin, target.checkout).length < units) return { kind: 'invalid', reason: 'no_free_bed' }
    } else {
      const conflict = unitConflict(ctx, null, target.roomId, target.bedId, target.checkin, target.checkout)
      if (conflict) return { kind: 'invalid', reason: conflict.type === 'stay' ? 'occupied' : 'blocked', conflict }
    }
  }
  const shortfall = unitsShortfall(ctx, inventoryCategory(ctx, target.roomId, target.roomTypeId), target.checkin, target.checkout, units)
  if (shortfall) return { kind: 'invalid', reason: 'no_units', conflict: shortfall }
  return { kind: 'ok' }
}

/** The calendar with one stay moved (optimistic update); everything else is shared with the original. */
export function applyPlacement(data: CalendarData, stayId: string, placement: Placement): CalendarData {
  return {
    ...data,
    stays: data.stays.map((stay) =>
      stay.id === stayId
        ? {
            ...stay,
            room_type_id: placement.roomTypeId,
            room_id: placement.roomId,
            bed_id: placement.bedId,
            checkin: placement.checkin,
            checkout: placement.checkout,
          }
        : stay,
    ),
  }
}

/**
 * How to take back a room move (same dates, same price): the previous room — with `force` if it was an
 * upgrade — or no room. `null` when dates or prices changed (a new quote cannot be undone exactly).
 */
export function undoSteps(plan: ChangePlan, ctx: PlanContext): Step[] | null {
  if (plan.confirm !== 'none' || !plan.primary) return null
  const { from } = plan
  if (from.roomId === null) return [{ op: 'unassign' }]
  const force = ctx.roomTypeOfRoom.get(from.roomId)?.id !== from.roomTypeId
  return [{ op: 'assign', body: { room_id: from.roomId, bed_id: from.bedId, ...(force ? { force } : {}) } }]
}

/** Where a drag (pointer or keyboard) would land: the row under it, the stay's new place and what it takes. */
export interface DropPreview {
  rowIndex: number
  /** `null` over a row that cannot take a stay (a category summary). */
  target: MoveTarget | null
  result: PlanResult | null
}

/**
 * The preview of a drag of `stay` from `origin` by `delta` px: moving the whole stay (rows and whole days) or
 * stretching its departure. `null` when it is outside the rows. The UI draws `target` as a ghost and, on
 * drop, runs `result`.
 */
export function previewDrop(
  stay: CalStay,
  origin: { rowIndex: number; lane: number },
  delta: { x: number; y: number },
  mode: DragMode,
  rows: readonly CalendarRow[],
  dayWidth: number,
  ctx: PlanContext,
): DropPreview | null {
  if (mode === 'resize') {
    const target = resizeTarget(stay, roundDays(delta.x, dayWidth), ctx.businessDate)
    return { rowIndex: origin.rowIndex, target, result: planChange(stay, target, ctx) }
  }
  const landing = resolveMove(rows, dayWidth, origin.rowIndex, origin.lane, delta)
  if (!landing) return null
  const place = targetForRow(rows[landing.rowIndex])
  if (!place) return { rowIndex: landing.rowIndex, target: null, result: null }
  const target: MoveTarget = {
    ...place,
    checkin: addDays(stay.checkin, landing.dayDelta),
    checkout: addDays(stay.checkout, landing.dayDelta),
  }
  return { rowIndex: landing.rowIndex, target, result: planChange(stay, target, ctx) }
}
