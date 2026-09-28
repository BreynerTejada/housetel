import { describe, expect, it } from 'vitest'
import type { CalendarCell, CalendarResponse } from '../api'
import { buildHeatmap, columnPendingIds, pruneSelection, rowPendingIds, toggleIds } from '../lib/heatmap'

function cell(id: string, status: CalendarCell['status'], change = '12.00'): CalendarCell {
  return { id, status, change_percent: change, current_price: '300000.00', recommended_price: '336000.00', occupancy: '40.00' }
}

const DBL = { id: 'rt-dbl', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, color: '#4e6c88' }
const STE = { id: 'rt-ste', code: 'STE', name: { es: 'Suite', en: 'Suite' }, color: '#b4583b' }
const FLEX = { id: 'plan-flex', code: 'FLEX', name: { es: 'Tarifa flexible', en: 'Flexible rate' } }

/** Thursday 29 Oct 2026 → Monday 2 Nov (a Monday holiday: its Saturday and Sunday are a long weekend). */
const CALENDAR: CalendarResponse = {
  start: '2026-10-29',
  end: '2026-11-03',
  business_date: '2026-10-30',
  currency: 'COP',
  dates: ['2026-10-29', '2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02'],
  holidays: [
    { date: '2026-11-01', name: 'Todos los Santos' },
    { date: '2026-11-02', name: 'Todos los Santos (observado)' },
  ],
  rows: [
    {
      room_type: DBL,
      rate_plan: FLEX,
      cells: {
        '2026-10-31': cell('a', 'pending'),
        '2026-11-01': cell('b', 'applied'),
        '2026-11-02': cell('c', 'pending', '-8.00'),
      },
    },
    { room_type: STE, rate_plan: FLEX, cells: { '2026-10-31': cell('d', 'pending'), '2026-10-30': cell('e', 'rejected') } },
  ],
}

describe('buildHeatmap', () => {
  it('marks weekend nights, holidays, the business date and where a month starts', () => {
    const { columns } = buildHeatmap(CALENDAR, { showDecided: true })
    expect(columns.map((column) => [column.date, column.weekend, column.holiday, column.today, column.monthStart])).toEqual([
      ['2026-10-29', false, null, false, true], // the first column always names its month
      ['2026-10-30', true, null, true, false], // Friday night
      ['2026-10-31', true, null, false, false], // Saturday night
      ['2026-11-01', false, 'Todos los Santos', false, true],
      ['2026-11-02', false, 'Todos los Santos (observado)', false, false],
    ])
  })

  it('lays one row per category and plan with a cell per night, and collects the pending ids', () => {
    const model = buildHeatmap(CALENDAR, { showDecided: true })
    expect(model.rows.map((row) => row.cells.map((item) => item.cell?.id ?? null))).toEqual([
      [null, null, 'a', 'b', 'c'],
      [null, 'e', 'd', null, null],
    ])
    expect(model.pendingIds).toEqual(['a', 'c', 'd'])
  })

  it('can hide the nights already decided', () => {
    const model = buildHeatmap(CALENDAR, { showDecided: false })
    expect(model.rows.map((row) => row.cells.map((item) => item.cell?.id ?? null))).toEqual([
      [null, null, 'a', null, 'c'],
      [null, null, 'd', null, null],
    ])
  })
})

describe('selection', () => {
  const model = buildHeatmap(CALENDAR, { showDecided: true })

  it('takes the pending recommendations of a row or of a night', () => {
    expect(rowPendingIds(model.rows[0])).toEqual(['a', 'c'])
    expect(columnPendingIds(model, '2026-10-31')).toEqual(['a', 'd'])
    expect(columnPendingIds(model, '2026-11-01')).toEqual([]) // only an applied one
  })

  it('adds a group unless all of it is already selected, then removes it', () => {
    const some = toggleIds(new Set(['a']), ['a', 'd'])
    expect([...some].sort()).toEqual(['a', 'd'])
    expect([...toggleIds(some, ['a', 'd'])]).toEqual([])
    expect([...toggleIds(new Set(['c']), ['a'])].sort()).toEqual(['a', 'c'])
  })

  it('drops from the selection what is no longer pending on screen', () => {
    expect([...pruneSelection(new Set(['a', 'b', 'zzz']), model)]).toEqual(['a'])
  })
})
