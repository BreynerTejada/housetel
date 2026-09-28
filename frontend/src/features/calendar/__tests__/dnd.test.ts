import { describe, expect, it } from 'vitest'
import type { CalendarData, CalStay } from '../api'
import {
  applyPlacement,
  createPlanContext,
  keyboardDelta,
  planChange,
  previewDrop,
  resizeTarget,
  resolveMove,
  roundDays,
  targetForRow,
  undoSteps,
  type MoveTarget,
  type PlanResult,
} from '../lib/dnd'
import { buildRows, ROW_HEIGHT, type CalendarRow } from '../lib/layout'
import { BUSINESS_DATE, IDS, makeCalendar, RANGE_START } from './fixtures'

const W = 60

function setup() {
  const data = makeCalendar()
  const rows = buildRows(data, { rangeStart: RANGE_START, days: 7 })
  const ctx = createPlanContext(data, BUSINESS_DATE)
  const stay = (id: string) => data.stays.find((candidate) => candidate.id === id) as CalStay
  const row = (key: string) => rows.find((candidate) => candidate.key === key) as CalendarRow
  const index = (key: string) => rows.findIndex((candidate) => candidate.key === key)
  /** The stay dropped on a row, moved `days` days. */
  const drop = (id: string, key: string, days = 0): MoveTarget => {
    const s = stay(id)
    const target = targetForRow(row(key))
    if (!target) throw new Error(`${key} is not a drop target`)
    return { ...target, checkin: addDaysIso(s.checkin, days), checkout: addDaysIso(s.checkout, days) }
  }
  return { data, rows, ctx, stay, row, index, drop }
}

function addDaysIso(iso: string, days: number) {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d + days))
  return date.toISOString().slice(0, 10)
}

function plan(result: PlanResult) {
  if (result.kind !== 'plan') throw new Error(`expected a plan, got ${JSON.stringify(result)}`)
  return result.plan
}

describe('roundDays', () => {
  it('rounds a horizontal distance to whole days, symmetrically', () => {
    expect(roundDays(0.49 * W, W)).toBe(0)
    expect(roundDays(0.5 * W, W)).toBe(1)
    expect(roundDays(-0.5 * W, W)).toBe(-1)
    expect(roundDays(-0.2 * W, W)).toBe(0)
    expect(Object.is(roundDays(-0.2 * W, W), -0)).toBe(false)
    expect(roundDays(2.6 * W, W)).toBe(3)
  })
})

describe('resolveMove: where a dragged bar lands', () => {
  it('keeps the row and counts whole days for a horizontal drag', () => {
    const { rows, index } = setup()
    const origin = index(`room:${IDS.r101}`)
    expect(resolveMove(rows, W, origin, 0, { x: 2 * W + 10, y: 4 })).toEqual({ rowIndex: origin, dayDelta: 2 })
  })

  it('follows the center of the bar to the row below or above', () => {
    const { rows, index } = setup()
    const origin = index(`room:${IDS.r101}`)
    expect(resolveMove(rows, W, origin, 0, { x: 0, y: ROW_HEIGHT.roomLane })).toEqual({
      rowIndex: index(`room:${IDS.r102}`),
      dayDelta: 0,
    })
    const up = resolveMove(rows, W, origin, 0, { x: -W, y: -ROW_HEIGHT.unassignedLane })
    expect(up).toEqual({ rowIndex: index(`un:${IDS.dbl}:1`), dayDelta: -1 })
  })

  it('lands nowhere outside the rows', () => {
    const { rows, index } = setup()
    expect(resolveMove(rows, W, index(`room:${IDS.r101}`), 0, { x: 0, y: -2000 })).toBeNull()
    expect(resolveMove(rows, W, index(`room:${IDS.r101}`), 0, { x: 0, y: 20_000 })).toBeNull()
  })
})

describe('keyboardDelta: arrow keys move a picked-up bar one day or one row at a time', () => {
  it('moves one whole day right or left, keeping the row', () => {
    const { rows, index } = setup()
    const origin = { rowIndex: index(`room:${IDS.r101}`), lane: 0 }
    expect(keyboardDelta(rows, W, origin, { x: 0, y: 0 }, 'ArrowRight')).toEqual({ x: W, y: 0 })
    expect(keyboardDelta(rows, W, origin, { x: W, y: 0 }, 'ArrowLeft')).toEqual({ x: 0, y: 0 })
    expect(keyboardDelta(rows, W, origin, { x: 0, y: 0 }, 'ArrowLeft')).toEqual({ x: -W, y: 0 })
  })

  it('goes to the next row that can take the stay (category rows are skipped) and resolveMove lands there', () => {
    const { rows, index } = setup()
    const origin = { rowIndex: index(`room:${IDS.r102}`), lane: 0 }
    const down = keyboardDelta(rows, W, origin, { x: 0, y: 0 }, 'ArrowDown')
    expect(down).not.toBeNull()
    expect(resolveMove(rows, W, origin.rowIndex, 0, down!)).toEqual({ rowIndex: index(`un:${IDS.ste}:0`), dayDelta: 0 })

    const back = keyboardDelta(rows, W, origin, down!, 'ArrowUp')
    expect(resolveMove(rows, W, origin.rowIndex, 0, back!)).toEqual({ rowIndex: origin.rowIndex, dayDelta: 0 })
  })

  it('keeps the days already moved when changing rows', () => {
    const { rows, index } = setup()
    const origin = { rowIndex: index(`un:${IDS.dbl}:1`), lane: 0 }
    const moved = keyboardDelta(rows, W, origin, { x: 2 * W, y: 0 }, 'ArrowDown')
    expect(resolveMove(rows, W, origin.rowIndex, 0, moved!)).toEqual({ rowIndex: index(`room:${IDS.r101}`), dayDelta: 2 })
  })

  it('stops at the first and last rows, ignores other keys and never changes rows while resizing', () => {
    const { rows, index } = setup()
    const first = { rowIndex: index(`un:${IDS.dbl}:0`), lane: 0 }
    expect(keyboardDelta(rows, W, first, { x: 0, y: 0 }, 'ArrowUp')).toBeNull()
    const last = { rowIndex: index(`bed:${IDS.bedB}`), lane: 0 }
    expect(keyboardDelta(rows, W, last, { x: 0, y: 0 }, 'ArrowDown')).toBeNull()
    expect(keyboardDelta(rows, W, first, { x: 0, y: 0 }, 'KeyA')).toBeNull()
    expect(keyboardDelta(rows, W, first, { x: 0, y: 0 }, 'ArrowDown', 'resize')).toBeNull()
    expect(keyboardDelta(rows, W, first, { x: 0, y: 0 }, 'ArrowRight', 'resize')).toEqual({ x: W, y: 0 })
  })
})

describe('targetForRow', () => {
  it('turns a row into where a stay would go (category rows are not drop targets)', () => {
    const { row } = setup()
    expect(targetForRow(row(`rt:${IDS.dbl}`))).toBeNull()
    expect(targetForRow(row(`un:${IDS.dbl}:1`))).toEqual({ roomTypeId: IDS.dbl, roomId: null, bedId: null })
    expect(targetForRow(row(`room:${IDS.r102}`))).toEqual({ roomTypeId: IDS.dbl, roomId: IDS.r102, bedId: null })
    expect(targetForRow(row(`dorm:${IDS.d1}`))).toEqual({ roomTypeId: IDS.dorm, roomId: IDS.d1, bedId: null })
    expect(targetForRow(row(`bed:${IDS.bedB}`))).toEqual({ roomTypeId: IDS.dorm, roomId: IDS.d1, bedId: IDS.bedB })
  })
})

describe('planChange: a drop becomes API calls', () => {
  it('drag right: new dates for the same room, confirmed before running, without repricing agreed nights', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('laura'), drop('laura', `room:${IDS.r101}`, 1), ctx))
    expect(result.confirm).toBe('dates')
    expect(result.primary?.steps).toEqual([
      { op: 'modify', body: { checkin: '2026-10-14', checkout: '2026-10-16', reprice: false } },
    ])
    expect(result.primary?.next).toEqual({
      roomTypeId: IDS.dbl,
      roomId: IDS.r101,
      bedId: null,
      checkin: '2026-10-14',
      checkout: '2026-10-16',
    })
    expect(result.upgrade).toBeNull()
  })

  it('drag down to a free room of the same category: assign right away', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('luis'), drop('luis', `room:${IDS.r101}`), ctx))
    expect(result.confirm).toBe('none')
    expect(result.primary?.steps).toEqual([{ op: 'assign', body: { room_id: IDS.r101, bed_id: null } }])
    expect(result.from).toMatchObject({ roomId: null, checkin: '2026-10-15' })
  })

  it('diagonal drag: change the dates first, then take the room', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('luis'), drop('luis', `room:${IDS.r101}`, 1), ctx))
    expect(result.confirm).toBe('dates')
    expect(result.primary?.steps).toEqual([
      { op: 'modify', body: { checkin: '2026-10-16', checkout: '2026-10-18', reprice: false } },
      { op: 'assign', body: { room_id: IDS.r101, bed_id: null } },
    ])
  })

  it('refuses a room taken by another stay on those nights, naming it', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('laura'), drop('laura', `room:${IDS.r102}`), ctx)).toEqual({
      kind: 'invalid',
      reason: 'occupied',
      conflict: { type: 'stay', code: 'HT-MATEO2', guest: 'Mateo Ruiz' },
    })
  })

  it('refuses a blocked room, telling why it is blocked', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('luis'), drop('luis', `room:${IDS.r102}`), ctx)).toEqual({
      kind: 'invalid',
      reason: 'blocked',
      conflict: { type: 'block', kind: 'maintenance', reason: 'Pintura' },
    })
  })

  it('ignores stays that already checked out when looking for conflicts', () => {
    const { ctx, stay, drop } = setup()
    // Pedro (checked out) left room 101 on the 12th; Luis arrives on the 15th.
    expect(planChange(stay('luis'), drop('luis', `room:${IDS.r101}`), ctx).kind).toBe('plan')
  })

  it('drag to the unassigned row: take the room away', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('laura'), drop('laura', `un:${IDS.dbl}:0`), ctx))
    expect(result.confirm).toBe('none')
    expect(result.primary?.steps).toEqual([{ op: 'unassign' }])
    expect(result.primary?.next).toMatchObject({ roomId: null, bedId: null, roomTypeId: IDS.dbl })
  })

  it('a room of another category: reprice in the new category, or move as an upgrade keeping the price', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('ana'), drop('ana', `room:${IDS.r301}`), ctx))
    expect(result.confirm).toBe('category')
    expect(result.primary?.steps).toEqual([
      { op: 'modify', body: { room_type_id: IDS.ste, reprice: true } },
      { op: 'assign', body: { room_id: IDS.r301, bed_id: null } },
    ])
    expect(result.primary?.next.roomTypeId).toBe(IDS.ste)
    expect(result.upgrade?.steps).toEqual([{ op: 'assign', body: { room_id: IDS.r301, bed_id: null, force: true } }])
    expect(result.upgrade?.next.roomTypeId).toBe(IDS.dbl)
  })

  it('moving an upgraded stay along its own room only changes the dates, not the category', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('sofia'), drop('sofia', `room:${IDS.r301}`, -1), ctx))
    expect(result.confirm).toBe('dates')
    expect(result.primary?.steps).toEqual([
      { op: 'modify', body: { checkin: '2026-10-15', checkout: '2026-10-17', reprice: false } },
    ])
    expect(result.primary?.next).toMatchObject({ roomTypeId: IDS.dbl, roomId: IDS.r301 })
  })

  it('an in-house guest can only move to another category as an upgrade', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('mateo'), drop('mateo', `room:${IDS.r301}`), ctx))
    expect(result.confirm).toBe('category')
    expect(result.primary).toBeNull()
    expect(result.upgrade?.steps).toEqual([{ op: 'assign', body: { room_id: IDS.r301, bed_id: null, force: true } }])
  })

  it('the unassigned row of another category changes the category and reprices, without a room', () => {
    const { ctx, stay, drop } = setup()
    const result = plan(planChange(stay('ana'), drop('ana', `un:${IDS.ste}:0`), ctx))
    expect(result.confirm).toBe('category')
    expect(result.primary?.steps).toEqual([{ op: 'modify', body: { room_type_id: IDS.ste, reprice: true } }])
    expect(result.upgrade).toBeNull()
  })

  it('beds: a free bed is assigned with its id; a dorm row takes any free bed of the room', () => {
    const { ctx, stay, drop } = setup()
    expect(plan(planChange(stay('carl'), drop('carl', `bed:${IDS.bedB}`), ctx)).primary?.steps).toEqual([
      { op: 'assign', body: { room_id: IDS.d1, bed_id: IDS.bedB } },
    ])
    // Bed A is Beatriz's on the 13th but bed B is free.
    expect(plan(planChange(stay('carl'), drop('carl', `dorm:${IDS.d1}`), ctx)).primary?.steps).toEqual([
      { op: 'assign', body: { room_id: IDS.d1, bed_id: null } },
    ])
  })

  it('beds: a whole-room block blocks every bed of the dorm', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('carl'), drop('carl', `bed:${IDS.bedB}`, 3), ctx)).toMatchObject({
      kind: 'invalid',
      reason: 'blocked',
      conflict: { type: 'block', reason: 'Fumigación' },
    })
    expect(planChange(stay('carl'), drop('carl', `dorm:${IDS.d1}`, 3), ctx)).toEqual({ kind: 'invalid', reason: 'no_free_bed' })
  })

  it('never mixes dorm beds and private rooms', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('bea'), drop('bea', `room:${IDS.r101}`), ctx)).toEqual({ kind: 'invalid', reason: 'kind_mismatch' })
  })

  it('refuses what the front desk cannot change', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('pedro'), drop('pedro', `room:${IDS.r102}`), ctx)).toEqual({ kind: 'invalid', reason: 'finished' })
    expect(planChange(stay('mateo'), drop('mateo', `room:${IDS.r102}`, 1), ctx)).toEqual({
      kind: 'invalid',
      reason: 'in_house_arrival',
    })
    expect(planChange(stay('mateo'), drop('mateo', `un:${IDS.dbl}:0`), ctx)).toEqual({
      kind: 'invalid',
      reason: 'in_house_unassign',
    })
    expect(planChange(stay('laura'), drop('laura', `room:${IDS.r101}`, -1), ctx)).toEqual({
      kind: 'invalid',
      reason: 'past_arrival',
    })
  })

  it('does nothing when the stay is dropped where it was', () => {
    const { ctx, stay, drop } = setup()
    expect(planChange(stay('laura'), drop('laura', `room:${IDS.r101}`), ctx)).toEqual({ kind: 'noop' })
    expect(planChange(stay('ana'), drop('ana', `un:${IDS.dbl}:1`), ctx)).toEqual({ kind: 'noop' })
    expect(planChange(stay('bea'), drop('bea', `dorm:${IDS.d1}`), ctx)).toEqual({ kind: 'noop' })
  })
})

describe('resizing the right edge', () => {
  it('extends or shortens the departure and keeps the agreed price of the nights that stay', () => {
    const { ctx, stay } = setup()
    const longer = plan(planChange(stay('laura'), resizeTarget(stay('laura'), 1, BUSINESS_DATE), ctx))
    expect(longer.confirm).toBe('dates')
    expect(longer.primary?.steps).toEqual([{ op: 'modify', body: { checkout: '2026-10-16', reprice: false } }])
  })

  it('never goes below one night, nor ends an in-house stay before the business date', () => {
    const { ctx, stay } = setup()
    expect(resizeTarget(stay('laura'), -5, BUSINESS_DATE).checkout).toBe('2026-10-14')
    const mateo = resizeTarget(stay('mateo'), -3, BUSINESS_DATE)
    expect(mateo.checkout).toBe(BUSINESS_DATE)
    expect(plan(planChange(stay('mateo'), mateo, ctx)).primary?.steps).toEqual([
      { op: 'modify', body: { checkout: BUSINESS_DATE, reprice: false } },
    ])
  })

  it('refuses to stretch over the next stay of the room', () => {
    const data: CalendarData = makeCalendar()
    data.stays.push({ ...data.stays[0], id: 'next', code: 'HT-NEXT01', guest_name: 'Nora Vélez', checkin: '2026-10-16', checkout: '2026-10-18' })
    const ctx = createPlanContext(data, BUSINESS_DATE)
    const laura = data.stays[0]
    expect(planChange(laura, resizeTarget(laura, 2, BUSINESS_DATE), ctx)).toMatchObject({
      kind: 'invalid',
      reason: 'occupied',
      conflict: { code: 'HT-NEXT01' },
    })
  })
})

describe('applyPlacement (optimistic update)', () => {
  it('moves the stay in a copy of the calendar and leaves the original alone', () => {
    const data = makeCalendar()
    const next = applyPlacement(data, 'luis', {
      roomTypeId: IDS.dbl,
      roomId: IDS.r101,
      bedId: null,
      checkin: '2026-10-16',
      checkout: '2026-10-18',
    })
    expect(next.stays.find((s) => s.id === 'luis')).toMatchObject({
      room_id: IDS.r101,
      checkin: '2026-10-16',
      checkout: '2026-10-18',
    })
    expect(data.stays.find((s) => s.id === 'luis')).toMatchObject({ room_id: null, checkin: '2026-10-15' })
    expect(next.room_types).toBe(data.room_types)
  })
})

describe('undoSteps', () => {
  it('puts a moved stay back where it was (unassigned, or the previous room with force if it was an upgrade)', () => {
    const { ctx, stay, drop } = setup()
    const assigned = plan(planChange(stay('luis'), drop('luis', `room:${IDS.r101}`), ctx))
    expect(undoSteps(assigned, ctx)).toEqual([{ op: 'unassign' }])

    const unassigned = plan(planChange(stay('laura'), drop('laura', `un:${IDS.dbl}:0`), ctx))
    expect(undoSteps(unassigned, ctx)).toEqual([{ op: 'assign', body: { room_id: IDS.r101, bed_id: null } }])

    const fromUpgrade = plan(planChange(stay('sofia'), drop('sofia', `un:${IDS.dbl}:0`), ctx))
    expect(undoSteps(fromUpgrade, ctx)).toEqual([{ op: 'assign', body: { room_id: IDS.r301, bed_id: null, force: true } }])
  })

  it('offers no undo when dates or prices changed', () => {
    const { ctx, stay, drop } = setup()
    expect(undoSteps(plan(planChange(stay('laura'), drop('laura', `room:${IDS.r101}`, 1), ctx)), ctx)).toBeNull()
  })
})

describe('previewDrop: where a drag would land and what it would do', () => {
  it('moves the whole stay by rows and days', () => {
    const { rows, ctx, stay, index } = setup()
    const preview = previewDrop(stay('luis'), { rowIndex: index(`un:${IDS.dbl}:1`), lane: 0 }, { x: W, y: 36 }, 'move', rows, W, ctx)
    expect(preview?.rowIndex).toBe(index(`room:${IDS.r101}`))
    expect(preview?.target).toEqual({ roomTypeId: IDS.dbl, roomId: IDS.r101, bedId: null, checkin: '2026-10-16', checkout: '2026-10-18' })
    expect(preview?.result?.kind).toBe('plan')
  })

  it('stretching only moves the departure and stays in the row', () => {
    const { rows, ctx, stay, index } = setup()
    const origin = { rowIndex: index(`room:${IDS.r101}`), lane: 0 }
    const preview = previewDrop(stay('laura'), origin, { x: 1.6 * W, y: 300 }, 'resize', rows, W, ctx)
    expect(preview?.rowIndex).toBe(origin.rowIndex)
    expect(preview?.target).toMatchObject({ roomId: IDS.r101, checkin: '2026-10-13', checkout: '2026-10-17' })
  })

  it('has no target over a category row and nothing at all outside the rows', () => {
    const { rows, ctx, stay, index } = setup()
    const origin = { rowIndex: index(`room:${IDS.r101}`), lane: 0 }
    // Room 101 → up past both unassigned lanes to the category row.
    const overCategory = previewDrop(stay('laura'), origin, { x: 0, y: -(20 + 64 + 10) }, 'move', rows, W, ctx)
    expect(overCategory).toEqual({ rowIndex: index(`rt:${IDS.dbl}`), target: null, result: null })
    expect(previewDrop(stay('laura'), origin, { x: 0, y: -5000 }, 'move', rows, W, ctx)).toBeNull()
  })
})
