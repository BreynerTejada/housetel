import { describe, expect, it } from 'vitest'
import type { RatePlan, Season } from '../api'
import {
  adjustmentEntries,
  derivedPrice,
  monthCells,
  planFamilies,
  seasonOn,
  signedPercent,
  weekdayPrice,
} from '../lib/plans'
import { derivationLabel } from '../lib/text'
import { FLEX, NR } from './fixtures'

const BB: RatePlan = { ...NR, id: 'plan-bb', code: 'BB', derivation_type: 'amount', derivation_value: '35000.00', sort_order: 30 }
const PROMO: RatePlan = { ...NR, id: 'plan-promo', code: 'PROMO', derivation_type: 'amount', derivation_value: '-400000.00', sort_order: 40 }

describe('derived prices', () => {
  it('applies a percentage or an amount to the base price, rounded to whole pesos', () => {
    expect(derivedPrice('320000.00', NR)).toBe(281600)
    expect(derivedPrice('420000.00', NR)).toBe(369600)
    expect(derivedPrice('320000.00', BB)).toBe(355000)
    expect(derivedPrice('333333.00', { derivation_type: 'percent', derivation_value: '-12.5' })).toBe(291666) // 291666.375
    expect(derivedPrice('100001.00', { derivation_type: 'percent', derivation_value: '-50' })).toBe(50001) // 50000.5 rounds up
  })

  it('never goes below zero', () => {
    expect(derivedPrice('320000.00', PROMO)).toBe(0)
    expect(derivedPrice('320000.00', { derivation_type: 'percent', derivation_value: '-150' })).toBe(0)
  })
})

describe('labels of adjustments', () => {
  it('write numbers the way the language on screen does', () => {
    expect(signedPercent(7.5, 'es')).toBe('+7,5 %')
    expect(signedPercent(7.5, 'en')).toBe('+7.5 %')
    expect(signedPercent(-12, 'en')).toBe('−12 %')
    expect(derivationLabel('percent', '-12.50', 'COP', 'es')).toBe('−12,5 %')
    expect(derivationLabel('percent', '-12.50', 'COP', 'en')).toBe('−12.5 %')
    expect(derivationLabel('amount', '35000.00', 'COP', 'en')).toMatch(/^\+ \$\s35[.,]000$/)
  })
})

describe('plan families', () => {
  it('groups every derived plan under its base plan, in plan order', () => {
    const other: RatePlan = { ...FLEX, id: 'plan-corp', code: 'CORP', sort_order: 5, children: [] }
    const families = planFamilies([BB, FLEX, NR, other])
    expect(families.map((family) => [family.base.code, family.derived.map((plan) => plan.code)])).toEqual([
      ['CORP', []],
      ['FLEX', ['NR', 'BB']],
    ])
  })
})

describe('weekday adjustments', () => {
  it('lists the adjusted days in week order, skipping zeros', () => {
    expect(adjustmentEntries({ sat: 15, mon: 0, fri: 10 })).toEqual([
      ['fri', 10],
      ['sat', 15],
    ])
    expect(adjustmentEntries({})).toEqual([])
  })

  it('prices a weekday like the quote engine (Monday = 0)', () => {
    expect(weekdayPrice('320000.00', { fri: 15, sat: 15 }, 4)).toBe(368000)
    expect(weekdayPrice('320000.00', { fri: 15, sat: 15 }, 0)).toBe(320000)
  })
})

const season = (id: string, start_date: string, end_date: string, priority: number): Season => ({
  id,
  name: id,
  start_date,
  end_date,
  priority,
  color: '#B98A2E',
  rates: [],
})

describe('season of a day', () => {
  const high = season('high', '2026-12-15', '2027-01-15', 10)
  const christmas = season('christmas', '2026-12-24', '2026-12-26', 20)
  const low = season('low', '2026-12-01', '2026-12-31', 10)

  it('uses inclusive end dates and the highest priority', () => {
    expect(seasonOn([high, christmas], '2027-01-15')?.id).toBe('high')
    expect(seasonOn([high, christmas], '2027-01-16')).toBeNull()
    expect(seasonOn([high, christmas], '2026-12-25')?.id).toBe('christmas')
  })

  it('breaks priority ties with the season that starts last', () => {
    expect(seasonOn([low, high], '2026-12-20')?.id).toBe('high')
    expect(seasonOn([high, low], '2026-12-20')?.id).toBe('high')
  })
})

describe('month grid', () => {
  it('starts the weeks on Monday with empty cells before the first day', () => {
    const cells = monthCells(2026, 9) // October 2026 starts on a Thursday
    expect(cells.slice(0, 4)).toEqual([null, null, null, '2026-10-01'])
    expect(cells.filter(Boolean)).toHaveLength(31)
    expect(cells.at(-1)).toBe('2026-10-31')
  })
})
