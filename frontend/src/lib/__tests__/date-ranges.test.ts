import { describe, expect, it } from 'vitest'
import { rangePreset } from '@/lib/date-ranges'

// 2026-10-01 is a Thursday. Ranges are inclusive on both ends (report style).
const today = '2026-10-01'

describe('rangePreset', () => {
  it.each([
    ['today', '2026-10-01', '2026-10-01'],
    ['yesterday', '2026-09-30', '2026-09-30'],
    ['tomorrow', '2026-10-02', '2026-10-02'],
    ['thisWeek', '2026-09-28', '2026-10-04'],
    ['next7', '2026-10-01', '2026-10-07'],
    ['thisMonth', '2026-10-01', '2026-10-31'],
    ['lastMonth', '2026-09-01', '2026-09-30'],
    ['last30', '2026-09-02', '2026-10-01'],
  ] as const)('%s', (preset, from, to) => {
    expect(rangePreset(preset, today)).toEqual({ from, to })
  })

  it('crosses the year boundary', () => {
    expect(rangePreset('lastMonth', '2027-01-15')).toEqual({ from: '2026-12-01', to: '2026-12-31' })
  })
})
