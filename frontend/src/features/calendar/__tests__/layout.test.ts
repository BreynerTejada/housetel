import { describe, expect, it } from 'vitest'
import type { CalendarData } from '../api'
import {
  assignLanes,
  barMetrics,
  buildRows,
  dayWidthFor,
  defaultCollapsed,
  resolveCollapsed,
  ROW_HEIGHT,
  rowIndexAt,
  stayColumns,
  totalHeight,
  type CalendarRow,
} from '../lib/layout'
import { IDS, makeBlock, makeCalendar, makeStay, RANGE_START } from './fixtures'

const WEEK = { rangeStart: RANGE_START, days: 7 } // Mon 12 → Sun 18 October 2026

function keys(rows: CalendarRow[]) {
  return rows.map((row) => row.key)
}

function itemIds(row: CalendarRow | undefined) {
  return (row?.items ?? []).map((item) => item.id)
}

function rowOf(rows: CalendarRow[], key: string) {
  const row = rows.find((candidate) => candidate.key === key)
  if (!row) throw new Error(`no row ${key}`)
  return row
}

describe('stayColumns: bars run from the middle of the arrival day to the middle of the departure day', () => {
  it('places a stay inside the range in column units (checkin at +0.5, checkout exclusive)', () => {
    expect(stayColumns('2026-10-13', '2026-10-15', RANGE_START, 7)).toEqual({
      start: 1.5,
      end: 3.5,
      clippedStart: false,
      clippedEnd: false,
    })
  })

  it('gives one night exactly one column of width: the checkout day is not a night', () => {
    const span = stayColumns('2026-10-12', '2026-10-13', RANGE_START, 7)
    expect(span).toEqual({ start: 0.5, end: 1.5, clippedStart: false, clippedEnd: false })
  })

  it('clips a stay that started before the range at the left edge', () => {
    expect(stayColumns('2026-10-10', '2026-10-14', RANGE_START, 7)).toEqual({
      start: 0,
      end: 2.5,
      clippedStart: true,
      clippedEnd: false,
    })
  })

  it('still shows the morning of a departure on the first day of the range', () => {
    expect(stayColumns('2026-10-09', '2026-10-12', RANGE_START, 7)).toEqual({
      start: 0,
      end: 0.5,
      clippedStart: true,
      clippedEnd: false,
    })
  })

  it('clips a stay that goes on after the last day at the right edge', () => {
    expect(stayColumns('2026-10-17', '2026-10-22', RANGE_START, 7)).toEqual({
      start: 5.5,
      end: 7,
      clippedStart: false,
      clippedEnd: true,
    })
    expect(stayColumns('2026-10-18', '2026-10-20', RANGE_START, 7)).toEqual({
      start: 6.5,
      end: 7,
      clippedStart: false,
      clippedEnd: true,
    })
  })

  it('leaves out stays that do not touch the range', () => {
    expect(stayColumns('2026-10-19', '2026-10-21', RANGE_START, 7)).toBeNull()
    expect(stayColumns('2026-10-01', '2026-10-11', RANGE_START, 7)).toBeNull()
  })
})

describe('dayWidthFor', () => {
  it('fills the width available after the room column, never below the minimum of the span', () => {
    expect(dayWidthFor(1212, 7, 212)).toBe(142) // (1212 − 212) / 7
    expect(dayWidthFor(1212, 30, 212)).toBe(42) // 33 → minimum for 30 days
    expect(dayWidthFor(375, 14, 104)).toBe(60) // phone: minimum, the grid scrolls sideways
    expect(dayWidthFor(0, 7, 212)).toBe(96) // not measured yet
    expect(dayWidthFor(5000, 7, 212)).toBe(200) // capped
  })
})

describe('barMetrics', () => {
  it('places bars inside their lane with an inset, by kind of row', () => {
    expect(barMetrics('room', 0)).toEqual({ top: 5, height: 30 })
    expect(barMetrics('room', 1)).toEqual({ top: 45, height: 30 })
    expect(barMetrics('bed', 0)).toEqual({ top: 4, height: 24 })
    expect(barMetrics('unassigned', 0)).toEqual({ top: 4, height: 24 })
    expect(barMetrics('dorm', 0)).toEqual({ top: 4, height: 22 })
  })
})

describe('assignLanes', () => {
  it('stacks overlapping items and lets a departure and an arrival on the same day share a lane', () => {
    const items = [
      { start: 1.5, end: 3.5 }, // A
      { start: 3.5, end: 5.5 }, // B: arrives the day A leaves → same lane
      { start: 2.5, end: 4.5 }, // C: overlaps A and B → second lane
      { start: 0, end: 1.5 }, // D: before A → first lane
    ]
    expect(assignLanes(items)).toEqual({ lanes: 2, laneOf: [0, 0, 1, 0] })
  })

  it('returns no lanes for nothing', () => {
    expect(assignLanes([])).toEqual({ lanes: 0, laneOf: [] })
  })
})

describe('buildRows', () => {
  it('lists each category, its unassigned lanes, its rooms and, in dorms, the room and its beds', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    expect(keys(rows)).toEqual([
      `rt:${IDS.dbl}`,
      `un:${IDS.dbl}:0`,
      `un:${IDS.dbl}:1`,
      `room:${IDS.r101}`,
      `room:${IDS.r102}`,
      `rt:${IDS.ste}`,
      `un:${IDS.ste}:0`,
      `room:${IDS.r301}`,
      `rt:${IDS.dorm}`,
      `un:${IDS.dorm}:0`,
      `dorm:${IDS.d1}`,
      `bed:${IDS.bedA}`,
      `bed:${IDS.bedB}`,
    ])
  })

  it('puts assigned stays in their room or bed row and unassigned ones in lanes of their category', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    expect(itemIds(rowOf(rows, `room:${IDS.r101}`))).toEqual(['pedro', 'laura'])
    expect(itemIds(rowOf(rows, `room:${IDS.r102}`))).toEqual(['mateo', 'block-102'])
    expect(itemIds(rowOf(rows, `bed:${IDS.bedA}`))).toEqual(['bea', 'block-d1'])
    expect(itemIds(rowOf(rows, `un:${IDS.dbl}:0`))).toEqual(['ana'])
    expect(itemIds(rowOf(rows, `un:${IDS.dbl}:1`))).toEqual(['luis'])
    expect(itemIds(rowOf(rows, `un:${IDS.dorm}:0`))).toEqual(['carl'])

    const first = rowOf(rows, `un:${IDS.dbl}:0`)
    expect(first).toMatchObject({ kind: 'unassigned', first: true, unassignedCount: 2 })
    expect(rowOf(rows, `un:${IDS.dbl}:1`)).toMatchObject({ first: false })
  })

  it('keeps the geometry of each bar in the row (clipped when it started before the range)', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    const mateo = rowOf(rows, `room:${IDS.r102}`).items.find((item) => item.id === 'mateo')
    expect(mateo?.span).toEqual({ start: 0, end: 2.5, clippedStart: true, clippedEnd: false })
  })

  it('flags an upgrade: the stay sits in a room of another category than the one booked', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    const suite = rowOf(rows, `room:${IDS.r301}`)
    expect(suite.items).toHaveLength(1)
    expect(suite.items[0]).toMatchObject({ type: 'stay', id: 'sofia', upgrade: true })
    expect(rowOf(rows, `room:${IDS.r101}`).items.every((item) => item.type === 'stay' && !item.upgrade)).toBe(true)
  })

  it('shows a whole-room dorm block on the dorm row and, inherited, on every bed', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    expect(itemIds(rowOf(rows, `dorm:${IDS.d1}`))).toEqual(['block-d1'])
    const bedB = rowOf(rows, `bed:${IDS.bedB}`)
    expect(bedB.items.map((item) => [item.id, item.type === 'block' && item.inherited])).toEqual([
      ['block-d1', true],
      ['block-bed-b', false],
    ])
  })

  it('counts the free beds of a dorm room per night (stays on beds and blocks take them)', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    // A: Beatriz 12–14. Whole room blocked the 16th. B blocked from the 17th.
    expect(rowOf(rows, `dorm:${IDS.d1}`).free).toEqual([1, 1, 1, 2, 0, 1, 1])
  })

  it('keeps counting beds taken by stays hidden by the status filter', () => {
    const rows = buildRows(makeCalendar(), { ...WEEK, statuses: new Set(['checked_in'] as const) })
    expect(rowOf(rows, `dorm:${IDS.d1}`).free).toEqual([1, 1, 1, 2, 0, 1, 1])
  })

  it('keeps an empty unassigned row per category as a slim drop target', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    const empty = rowOf(rows, `un:${IDS.ste}:0`)
    expect(empty).toMatchObject({ kind: 'unassigned', first: true, unassignedCount: 0, items: [] })
    expect(empty.height).toBe(ROW_HEIGHT.unassignedEmpty)
  })

  it('collapsing a category keeps only its summary row', () => {
    const rows = buildRows(makeCalendar(), { ...WEEK, collapsed: new Set([`rt:${IDS.dbl}`]) })
    expect(keys(rows).slice(0, 2)).toEqual([`rt:${IDS.dbl}`, `rt:${IDS.ste}`])
    expect(rowOf(rows, `rt:${IDS.dbl}`).collapsed).toBe(true)
  })

  it('collapsing the unassigned group leaves one row that counts the stays of each night', () => {
    const rows = buildRows(makeCalendar(), { ...WEEK, collapsed: new Set([`un:${IDS.dbl}`]) })
    const group = rows.filter((row) => row.key.startsWith(`un:${IDS.dbl}`))
    expect(group).toHaveLength(1)
    expect(group[0]).toMatchObject({ collapsed: true, unassignedCount: 2, items: [] })
    // Ana: 14–15; Luis: 15–16.
    expect(group[0].counts).toEqual([0, 0, 1, 2, 1, 0, 0])
  })

  it('shows only the chosen categories and statuses', () => {
    const rows = buildRows(makeCalendar(), {
      ...WEEK,
      categories: new Set([IDS.dbl]),
      statuses: new Set(['confirmed', 'checked_in'] as const),
    })
    expect(rows.every((row) => row.roomType.id === IDS.dbl)).toBe(true)
    expect(itemIds(rowOf(rows, `room:${IDS.r101}`))).toEqual(['laura']) // Pedro (checked out) hidden
    expect(keys(rows).filter((key) => key.startsWith('un:'))).toEqual([`un:${IDS.dbl}:0`]) // Ana (tentative) hidden
    expect(itemIds(rowOf(rows, `un:${IDS.dbl}:0`))).toEqual(['luis'])
    expect(itemIds(rowOf(rows, `room:${IDS.r102}`))).toEqual(['mateo', 'block-102']) // blocks always show
  })

  it('stacks overlapping stays of one room in lanes and makes that row taller', () => {
    const data: CalendarData = makeCalendar()
    data.stays.push(
      makeStay({ id: 'over', room_id: IDS.r101, checkin: '2026-10-14', checkout: '2026-10-16' }), // overlaps Laura
    )
    const row = rowOf(buildRows(data, WEEK), `room:${IDS.r101}`)
    expect(row.lanes).toBe(2)
    expect(row.height).toBe(2 * ROW_HEIGHT.roomLane)
    expect(row.items.find((item) => item.id === 'over')?.lane).toBe(1)
  })

  it('leaves out stays and blocks outside the range', () => {
    const data = makeCalendar()
    data.blocks.push(makeBlock({ id: 'later', room_id: IDS.r101, start: '2026-10-25', end: '2026-10-27' }))
    expect(itemIds(rowOf(buildRows(data, WEEK), `room:${IDS.r101}`))).not.toContain('later')
  })

  it('starts with the unassigned group folded when it would take more than four lanes', () => {
    const data = makeCalendar()
    for (let i = 0; i < 5; i += 1) {
      data.stays.push(makeStay({ id: `walk${i}`, room_type_id: IDS.dorm, checkin: '2026-10-14', checkout: '2026-10-15', adults: 1 }))
    }
    // Stays outside the range take no lane.
    for (let i = 0; i < 5; i += 1) {
      data.stays.push(makeStay({ id: `later${i}`, room_type_id: IDS.dbl, checkin: '2026-11-02', checkout: '2026-11-04' }))
    }
    // D6: the five walk-ins overlap on the 14th → 5 lanes → folded. DBL: Ana and Luis → 2 lanes → open.
    expect(defaultCollapsed(data, WEEK)).toEqual(new Set([`un:${IDS.dorm}`]))
    expect(defaultCollapsed(makeCalendar(), WEEK)).toEqual(new Set())
  })

  it('counts lanes, not stays: many short stays one after another stay open', () => {
    const data = makeCalendar()
    // Seven one-night stays, each arriving the day the previous one leaves: one lane.
    for (let i = 0; i < 7; i += 1) {
      const day = `2026-10-1${2 + i}`
      data.stays.push(makeStay({ id: `chain${i}`, room_type_id: IDS.ste, checkin: day, checkout: `2026-10-1${3 + i}` }))
    }
    expect(defaultCollapsed(data, WEEK)).toEqual(new Set())
  })

  it('what the user folded or unfolded wins over the defaults, which keep applying to the rest', () => {
    const defaults = new Set([`un:${IDS.dorm}`, `un:${IDS.ste}`])
    const overrides = { [`un:${IDS.dorm}`]: false, [`rt:${IDS.dbl}`]: true }
    expect(resolveCollapsed(defaults, overrides)).toEqual(new Set([`un:${IDS.ste}`, `rt:${IDS.dbl}`]))
    expect(resolveCollapsed(new Set(), {})).toEqual(new Set())
  })

  it('stacks rows one after the other and finds the row under a vertical position', () => {
    const rows = buildRows(makeCalendar(), WEEK)
    expect(rows[0].offset).toBe(0)
    for (let i = 1; i < rows.length; i += 1) expect(rows[i].offset).toBe(rows[i - 1].offset + rows[i - 1].height)
    expect(totalHeight(rows)).toBe(rows.at(-1)!.offset + rows.at(-1)!.height)

    const room102 = rows.findIndex((row) => row.key === `room:${IDS.r102}`)
    expect(rowIndexAt(rows, rows[room102].offset)).toBe(room102)
    expect(rowIndexAt(rows, rows[room102].offset + rows[room102].height - 1)).toBe(room102)
    expect(rowIndexAt(rows, -1)).toBe(-1)
    expect(rowIndexAt(rows, totalHeight(rows))).toBe(-1)
  })
})
