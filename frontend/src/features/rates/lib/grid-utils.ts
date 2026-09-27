import type { BulkPayload, BulkSet, GridResponse, GridRow } from '../api'

// ---- Dates: API dates are `YYYY-MM-DD` calendar days; never go through UTC midnight ----------------

function toParts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split('-').map(Number)
  return [y, m, d]
}

function fromDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = toParts(iso)
  return fromDate(new Date(y, m - 1, d + days))
}

/** Monday = 0 … Sunday = 6 (the API convention for `weekdays` / `dow`). */
export function weekdayOf(iso: string): number {
  const [y, m, d] = toParts(iso)
  return (new Date(y, m - 1, d).getDay() + 6) % 7
}

/** Hotels sell the weekend as the nights of Friday and Saturday. */
export function isWeekendNight(iso: string): boolean {
  const day = weekdayOf(iso)
  return day === 4 || day === 5
}

/** Nights of the inclusive range `[from, to]` that fall on `weekdays` (empty = every weekday). */
export function countNights(from: string, to: string, weekdays: number[]): number {
  let count = 0
  for (let day = from; day <= to; day = addDays(day, 1)) {
    if (weekdays.length === 0 || weekdays.includes(weekdayOf(day))) count += 1
  }
  return count
}

// ---- Parsing what people type ------------------------------------------------------------------------

/**
 * An amount in whole pesos as the API string (`"320000"`), from what someone typed ("320.000", "$ 95 000").
 * Dots and spaces are thousands separators; anything after a decimal comma is dropped. `null` when invalid
 * or negative.
 */
export function parseAmount(typed: string): string | null {
  const text = typed.trim()
  if (!text || text.includes('-')) return null
  const [whole] = text.split(',')
  const digits = whole.replace(/[\s.$]/g, '')
  if (!/^\d+$/.test(digits)) return null
  return String(Number(digits))
}

/** A signed amount or percentage for relative changes ("-10", "15.000"); `null` when invalid. */
export function parseSigned(typed: string): string | null {
  const text = typed.trim()
  const negative = text.startsWith('-')
  const amount = parseAmount(negative ? text.slice(1) : text.replace(/^\+/, ''))
  if (amount === null) return null
  return negative && amount !== '0' ? `-${amount}` : amount
}

/** Length of stay: `''` → `null` (clear it), 1–365 → the number, anything else → `undefined` (invalid). */
export function parseLos(typed: string): number | null | undefined {
  const text = typed.trim()
  if (!text) return null
  if (!/^\d+$/.test(text)) return undefined
  const value = Number(text)
  return value >= 1 && value <= 365 ? value : undefined
}

// ---- Bulk edit ---------------------------------------------------------------------------------------

export type Tristate = 'keep' | 'on' | 'off'

export interface BulkForm {
  roomTypeIds: string[]
  /** Inclusive range of nights. */
  from: string
  to: string
  weekdays: number[]
  price: { mode: 'keep' | 'set' | 'percent' | 'amount'; value: string }
  minLos: { mode: 'keep' | 'set' | 'clear'; value: string }
  maxLos: { mode: 'keep' | 'set' | 'clear'; value: string }
  cta: Tristate
  ctd: Tristate
  stopSell: Tristate
}

export function emptyBulkForm(): BulkForm {
  return {
    roomTypeIds: [],
    from: '',
    to: '',
    weekdays: [],
    price: { mode: 'keep', value: '' },
    minLos: { mode: 'keep', value: '' },
    maxLos: { mode: 'keep', value: '' },
    cta: 'keep',
    ctd: 'keep',
    stopSell: 'keep',
  }
}

function priceChange(form: BulkForm): BulkSet {
  const { mode, value } = form.price
  if (mode === 'set') {
    const amount = parseAmount(value)
    return amount === null ? {} : { price: amount }
  }
  if (mode === 'percent') {
    const percent = parseSigned(value)
    return percent === null ? {} : { price_delta_percent: percent }
  }
  if (mode === 'amount') {
    const amount = parseSigned(value)
    return amount === null ? {} : { price_delta_amount: amount }
  }
  return {}
}

function losChange(change: BulkForm['minLos']): number | null | undefined {
  if (change.mode === 'clear') return null
  if (change.mode === 'set') return parseLos(change.value) ?? undefined
  return undefined
}

function flag(state: Tristate): boolean | undefined {
  return state === 'keep' ? undefined : state === 'on'
}

export function bulkSet(form: BulkForm): BulkSet {
  const set: BulkSet = { ...priceChange(form) }
  const minLos = losChange(form.minLos)
  const maxLos = losChange(form.maxLos)
  if (minLos !== undefined) set.min_los = minLos
  if (maxLos !== undefined) set.max_los = maxLos
  const cta = flag(form.cta)
  const ctd = flag(form.ctd)
  const stopSell = flag(form.stopSell)
  if (cta !== undefined) set.cta = cta
  if (ctd !== undefined) set.ctd = ctd
  if (stopSell !== undefined) set.stop_sell = stopSell
  return set
}

export function hasBulkChanges(form: BulkForm): boolean {
  return Object.keys(bulkSet(form)).length > 0
}

/**
 * A change that was chosen but whose value is missing or invalid (it would be left out of the payload
 * without a word): `'price'` (no amount, or a percentage below −100) or `'stay'` (not 1–365 nights).
 */
export function bulkFormError(form: BulkForm): 'price' | 'stay' | null {
  const { mode, value } = form.price
  if (mode !== 'keep') {
    const parsed = mode === 'set' ? parseAmount(value) : parseSigned(value)
    if (parsed === null || (mode === 'percent' && Number(parsed) < -100)) return 'price'
  }
  if ([form.minLos, form.maxLos].some((change) => change.mode === 'set' && typeof parseLos(change.value) !== 'number')) {
    return 'stay'
  }
  return null
}

export function buildBulkPayload(form: BulkForm, planId: string): BulkPayload {
  return {
    room_type_ids: form.roomTypeIds,
    rate_plan_id: planId,
    start: form.from,
    end: addDays(form.to, 1),
    weekdays: form.weekdays.length >= 7 ? [] : [...form.weekdays].sort((a, b) => a - b),
    set: bulkSet(form),
    source: 'bulk',
  }
}

// ---- Optimistic updates --------------------------------------------------------------------------------

export type CellField = 'price' | 'min_los' | 'cta' | 'ctd' | 'stop_sell'

export interface CellChange {
  roomTypeId: string
  date: string
  field: CellField
  value: string | number | boolean | null
}

function toMoney(value: string): string {
  return Number(value).toFixed(2)
}

/** The grid as it will look once `change` is saved (a new price is a manual price). */
export function applyCellChange(grid: GridResponse, change: CellChange): GridResponse {
  return {
    ...grid,
    room_types: grid.room_types.map((roomType) =>
      roomType.id !== change.roomTypeId
        ? roomType
        : {
            ...roomType,
            rows: roomType.rows.map((row): GridRow => {
              if (row.date !== change.date) return row
              if (change.field === 'price') return { ...row, price: toMoney(String(change.value)), source: 'manual' }
              return { ...row, [change.field]: change.value }
            }),
          },
    ),
  }
}

/** Undo of a failed optimistic change: the night gets back what `original` had for that field. */
export function restoreCell(grid: GridResponse, change: CellChange, original: GridRow): GridResponse {
  return {
    ...grid,
    room_types: grid.room_types.map((roomType) =>
      roomType.id !== change.roomTypeId
        ? roomType
        : {
            ...roomType,
            rows: roomType.rows.map((row): GridRow => {
              if (row.date !== change.date) return row
              if (change.field === 'price') return { ...row, price: original.price, source: original.source }
              return { ...row, [change.field]: original[change.field] }
            }),
          },
    ),
  }
}

/** One night of one category, saved from its cell (a `manual` change). */
export function cellPayload(change: CellChange, planId: string): BulkPayload {
  return {
    room_type_ids: [change.roomTypeId],
    rate_plan_id: planId,
    start: change.date,
    end: addDays(change.date, 1),
    weekdays: [],
    set: { [change.field]: change.value } as BulkSet,
    source: 'manual',
  }
}

// ---- Keyboard movement (roving focus inside the grid) ----------------------------------------------------

export interface Position {
  r: number
  c: number
}

const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max)

/** Next focused cell for a navigation key, or `null` when the key does not move the focus. */
export function moveFocus(
  pos: Position,
  key: string,
  dims: { rows: number; cols: number },
  mods: { ctrl?: boolean } = {},
): Position | null {
  const lastRow = dims.rows - 1
  const lastCol = dims.cols - 1
  switch (key) {
    case 'ArrowRight':
      return { r: pos.r, c: clamp(pos.c + 1, lastCol) }
    case 'ArrowLeft':
      return { r: pos.r, c: clamp(pos.c - 1, lastCol) }
    case 'ArrowDown':
      return { r: clamp(pos.r + 1, lastRow), c: pos.c }
    case 'ArrowUp':
      return { r: clamp(pos.r - 1, lastRow), c: pos.c }
    case 'Home':
      return mods.ctrl ? { r: 0, c: 0 } : { r: pos.r, c: 0 }
    case 'End':
      return mods.ctrl ? { r: lastRow, c: lastCol } : { r: pos.r, c: lastCol }
    default:
      return null
  }
}
