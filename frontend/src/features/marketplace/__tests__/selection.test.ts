import { describe, expect, it } from 'vitest'
import { parseItems, quantityLeft, selectionSummary, serializeItems, withQuantity, type SelectionItem } from '../lib/selection'

const DBL = '6ffbff0e-c5bf-4b8d-add8-bc49472b746d'
const STE = '1670a4e3-0000-4000-8000-000000000003'
const FLEX = 'fafa56fb-9421-42e7-a0a3-d453fc97ac2b'
const NR = 'aa11aa11-0000-4000-8000-000000000002'

const offer = (roomTypeId: string, ratePlanId: string, total: string, available = 2, needed = 1) => ({
  room_type_id: roomTypeId,
  rate_plan_id: ratePlanId,
  available_units: available,
  units_needed: needed,
  total,
})

describe('selection in the URL', () => {
  it('round-trips room type, plan and quantity', () => {
    const items: SelectionItem[] = [
      { roomTypeId: DBL, ratePlanId: FLEX, quantity: 2 },
      { roomTypeId: STE, ratePlanId: NR, quantity: 1 },
    ]

    const raw = serializeItems(items)

    expect(raw).toBe(`${DBL}:${FLEX}:2,${STE}:${NR}:1`)
    expect(parseItems(raw)).toEqual(items)
  })

  it('skips malformed entries and non-positive quantities', () => {
    expect(parseItems(`${DBL}:${FLEX}:0,garbage,${STE}:${NR}:x,${STE}:${NR}:3`)).toEqual([
      { roomTypeId: STE, ratePlanId: NR, quantity: 3 },
    ])
    expect(parseItems(null)).toEqual([])
  })

  it('merges repeated offers into one item', () => {
    expect(parseItems(`${DBL}:${FLEX}:1,${DBL}:${FLEX}:2`)).toEqual([{ roomTypeId: DBL, ratePlanId: FLEX, quantity: 3 }])
  })
})

describe('withQuantity', () => {
  it('adds, updates and removes an offer', () => {
    const one = withQuantity([], DBL, FLEX, 1)
    expect(one).toEqual([{ roomTypeId: DBL, ratePlanId: FLEX, quantity: 1 }])

    const two = withQuantity(one, DBL, FLEX, 2)
    expect(two).toEqual([{ roomTypeId: DBL, ratePlanId: FLEX, quantity: 2 }])

    expect(withQuantity(two, DBL, FLEX, 0)).toEqual([])
  })
})

describe('quantityLeft', () => {
  it('shares the units of a room type between its plans', () => {
    const offers = [offer(DBL, FLEX, '800000', 3), offer(DBL, NR, '700000', 3)]
    const items = [{ roomTypeId: DBL, ratePlanId: NR, quantity: 2 }]

    // 3 rooms of the type, 2 already taken by the other plan
    expect(quantityLeft(offers[0], items, offers)).toBe(1)
    // the plan's own quantity does not count against itself
    expect(quantityLeft(offers[1], items, offers)).toBe(3)
  })

  it('counts dorm beds per guest', () => {
    const dorm = offer(STE, FLEX, '150000', 7, 3)

    expect(quantityLeft(dorm, [], [dorm])).toBe(2)
  })
})

describe('selectionSummary', () => {
  it('adds the totals and counts the units of the selected offers', () => {
    const offers = [offer(DBL, FLEX, '818720.00'), offer(STE, NR, '1463462.00', 1)]
    const items = [
      { roomTypeId: DBL, ratePlanId: FLEX, quantity: 2 },
      { roomTypeId: STE, ratePlanId: NR, quantity: 1 },
    ]

    expect(selectionSummary(items, offers)).toEqual({ total: 3100902, rooms: 3, lines: 2 })
  })

  it('ignores items whose offer is no longer available', () => {
    expect(selectionSummary([{ roomTypeId: DBL, ratePlanId: NR, quantity: 1 }], [offer(DBL, FLEX, '1')])).toEqual({
      total: 0,
      rooms: 0,
      lines: 0,
    })
  })
})
