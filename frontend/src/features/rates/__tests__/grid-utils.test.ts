import { describe, expect, it } from 'vitest'
import type { GridResponse } from '../api'
import {
  addDays,
  applyCellChange,
  buildBulkPayload,
  cellPayload,
  countNights,
  emptyBulkForm,
  hasBulkChanges,
  isWeekendNight,
  moveFocus,
  parseAmount,
  parseLos,
  restoreCell,
  weekdayOf,
} from '../lib/grid-utils'

describe('dates (YYYY-MM-DD, local calendar days)', () => {
  it('adds days across months and years', () => {
    expect(addDays('2026-10-01', 1)).toBe('2026-10-02')
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })

  it('numbers weekdays from Monday = 0', () => {
    expect(weekdayOf('2026-10-12')).toBe(0) // Monday (Día de la Raza)
    expect(weekdayOf('2026-10-01')).toBe(3) // Thursday
    expect(weekdayOf('2026-10-04')).toBe(6) // Sunday
  })

  it('treats Friday and Saturday nights as the weekend of a hotel', () => {
    expect(['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'].map(isWeekendNight)).toEqual([false, true, true, false])
  })

  it('counts the nights of an inclusive range that fall on the chosen weekdays', () => {
    expect(countNights('2026-10-01', '2026-10-07', [])).toBe(7)
    expect(countNights('2026-10-01', '2026-10-07', [4, 5])).toBe(2)
    expect(countNights('2026-10-07', '2026-10-01', [])).toBe(0)
  })
})

describe('parsing what people type', () => {
  it.each([
    ['320000', '320000'],
    ['320.000', '320000'],
    ['$ 1.250.000', '1250000'],
    [' 95 000 ', '95000'],
    ['0', '0'],
  ])('reads %j as the amount %s (COP, whole pesos)', (typed, amount) => {
    expect(parseAmount(typed)).toBe(amount)
  })

  it.each(['', 'abc', '-5', '12-3'])('rejects %j as an amount', (typed) => {
    expect(parseAmount(typed)).toBeNull()
  })

  it('reads a length of stay: empty clears it, 1–365 are valid, anything else is invalid', () => {
    expect(parseLos('')).toBeNull()
    expect(parseLos(' 3 ')).toBe(3)
    expect(parseLos('0')).toBeUndefined()
    expect(parseLos('400')).toBeUndefined()
    expect(parseLos('2.5')).toBeUndefined()
    expect(parseLos('dos')).toBeUndefined()
  })
})

describe('bulk edit payload', () => {
  const base = { ...emptyBulkForm(), roomTypeIds: ['rt-2', 'rt-1'], from: '2026-10-01', to: '2026-10-07' }

  it('sends only what changes, with an exclusive end and sorted weekdays', () => {
    const payload = buildBulkPayload(
      {
        ...base,
        weekdays: [5, 4],
        price: { mode: 'set', value: '380.000' },
        minLos: { mode: 'set', value: '2' },
        cta: 'on',
        stopSell: 'off',
      },
      'plan-1',
    )
    expect(payload).toEqual({
      room_type_ids: ['rt-2', 'rt-1'],
      rate_plan_id: 'plan-1',
      start: '2026-10-01',
      end: '2026-10-08',
      weekdays: [4, 5],
      set: { price: '380000', min_los: 2, cta: true, stop_sell: false },
      source: 'bulk',
    })
  })

  it('maps relative price changes and cleared lengths of stay', () => {
    expect(
      buildBulkPayload({ ...base, price: { mode: 'percent', value: '-10' }, maxLos: { mode: 'clear', value: '' } }, 'p').set,
    ).toEqual({ price_delta_percent: '-10', max_los: null })
    expect(buildBulkPayload({ ...base, price: { mode: 'amount', value: '15.000' } }, 'p').set).toEqual({
      price_delta_amount: '15000',
    })
    expect(buildBulkPayload({ ...base, price: { mode: 'amount', value: '-15000' } }, 'p').set).toEqual({
      price_delta_amount: '-15000',
    })
  })

  it('sends every weekday as an empty list (all days)', () => {
    expect(buildBulkPayload({ ...base, weekdays: [6, 5, 4, 3, 2, 1, 0], ctd: 'on' }, 'p').weekdays).toEqual([])
  })

  it('knows when there is nothing to change', () => {
    expect(hasBulkChanges(base)).toBe(false)
    expect(hasBulkChanges({ ...base, ctd: 'on' })).toBe(true)
    expect(hasBulkChanges({ ...base, price: { mode: 'set', value: '' } })).toBe(false)
  })
})

describe('optimistic cell changes', () => {
  const grid: GridResponse = {
    rate_plan: null,
    currency: 'COP',
    start: '2026-10-01',
    end: '2026-10-03',
    dates: ['2026-10-01', '2026-10-02'],
    holidays: [],
    room_types: [
      {
        id: 'rt-1',
        code: 'DBL',
        name: { es: 'Estándar', en: 'Standard' },
        color: '#4E6C88',
        kind: 'private',
        rows: ['2026-10-01', '2026-10-02'].map((date) => ({
          date,
          price: '320000.00',
          extra_adult_price: '60000.00',
          extra_child_price: '30000.00',
          min_los: null,
          max_los: null,
          cta: false,
          ctd: false,
          stop_sell: false,
          source: 'season' as const,
          available: 4,
        })),
      },
    ],
  }

  it('a new price marks the night as manual and leaves the rest untouched', () => {
    const next = applyCellChange(grid, { roomTypeId: 'rt-1', date: '2026-10-02', field: 'price', value: '350000' })
    expect(next.room_types[0].rows[1]).toMatchObject({ price: '350000.00', source: 'manual' })
    expect(next.room_types[0].rows[0]).toBe(grid.room_types[0].rows[0])
    expect(grid.room_types[0].rows[1].price).toBe('320000.00')
  })

  it('a failed save puts back exactly what the night had', () => {
    const edited = applyCellChange(grid, { roomTypeId: 'rt-1', date: '2026-10-02', field: 'price', value: '1' })
    const original = grid.room_types[0].rows[1]
    const restored = restoreCell(edited, { roomTypeId: 'rt-1', date: '2026-10-02', field: 'price', value: '1' }, original)
    expect(restored.room_types[0].rows[1]).toEqual(original)
    const toggled = applyCellChange(grid, { roomTypeId: 'rt-1', date: '2026-10-01', field: 'stop_sell', value: true })
    const back = restoreCell(toggled, { roomTypeId: 'rt-1', date: '2026-10-01', field: 'stop_sell', value: true }, grid.room_types[0].rows[0])
    expect(back.room_types[0].rows[0].stop_sell).toBe(false)
  })

  it('restrictions keep the price source', () => {
    const next = applyCellChange(grid, { roomTypeId: 'rt-1', date: '2026-10-01', field: 'cta', value: true })
    expect(next.room_types[0].rows[0]).toMatchObject({ cta: true, source: 'season', price: '320000.00' })
    const cleared = applyCellChange(grid, { roomTypeId: 'rt-1', date: '2026-10-01', field: 'min_los', value: 3 })
    expect(cleared.room_types[0].rows[0].min_los).toBe(3)
  })
})

describe('single-cell edits', () => {
  it('save one night of one category as a manual change', () => {
    expect(cellPayload({ roomTypeId: 'rt-1', date: '2026-10-31', field: 'price', value: '350000' }, 'plan-1')).toEqual({
      room_type_ids: ['rt-1'],
      rate_plan_id: 'plan-1',
      start: '2026-10-31',
      end: '2026-11-01',
      weekdays: [],
      set: { price: '350000' },
      source: 'manual',
    })
    expect(cellPayload({ roomTypeId: 'rt-1', date: '2026-10-31', field: 'min_los', value: null }, 'p').set).toEqual({
      min_los: null,
    })
    expect(cellPayload({ roomTypeId: 'rt-1', date: '2026-10-31', field: 'cta', value: true }, 'p').set).toEqual({ cta: true })
  })
})

describe('keyboard movement', () => {
  const dims = { rows: 4, cols: 10 }

  it.each([
    ['ArrowRight', { r: 1, c: 3 }, { r: 1, c: 4 }],
    ['ArrowLeft', { r: 1, c: 3 }, { r: 1, c: 2 }],
    ['ArrowDown', { r: 1, c: 3 }, { r: 2, c: 3 }],
    ['ArrowUp', { r: 1, c: 3 }, { r: 0, c: 3 }],
    ['Home', { r: 1, c: 3 }, { r: 1, c: 0 }],
    ['End', { r: 1, c: 3 }, { r: 1, c: 9 }],
  ])('%s moves inside the grid', (key, from, to) => {
    expect(moveFocus(from, key, dims)).toEqual(to)
  })

  it('stops at the edges and ignores other keys', () => {
    expect(moveFocus({ r: 0, c: 0 }, 'ArrowUp', dims)).toEqual({ r: 0, c: 0 })
    expect(moveFocus({ r: 3, c: 9 }, 'ArrowRight', dims)).toEqual({ r: 3, c: 9 })
    expect(moveFocus({ r: 1, c: 1 }, 'a', dims)).toBeNull()
  })

  it('Ctrl+Home and Ctrl+End jump to the corners', () => {
    expect(moveFocus({ r: 2, c: 5 }, 'Home', dims, { ctrl: true })).toEqual({ r: 0, c: 0 })
    expect(moveFocus({ r: 2, c: 5 }, 'End', dims, { ctrl: true })).toEqual({ r: 3, c: 9 })
  })
})
