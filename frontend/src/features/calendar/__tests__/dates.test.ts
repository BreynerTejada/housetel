import { describe, expect, it } from 'vitest'
import { addDays, dayList, diffDays, isWeekendNight, weekdayOf, yearsBetween } from '../lib/dates'

describe('calendar dates (calendar days, never UTC midnight)', () => {
  it('adds days across months, years and the DST-free Bogotá calendar', () => {
    expect(addDays('2026-10-30', 3)).toBe('2026-11-02')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDays('2026-10-12', 0)).toBe('2026-10-12')
  })

  it('counts the days from one date to another (negative when going back)', () => {
    expect(diffDays('2026-10-12', '2026-10-14')).toBe(2)
    expect(diffDays('2026-10-14', '2026-10-12')).toBe(-2)
    expect(diffDays('2026-12-30', '2027-01-02')).toBe(3)
  })

  it('lists consecutive days from a start', () => {
    expect(dayList('2026-10-30', 4)).toEqual(['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02'])
    expect(dayList('2026-10-30', 0)).toEqual([])
  })

  it('numbers weekdays from Monday = 0 and treats Friday and Saturday nights as the weekend', () => {
    expect(weekdayOf('2026-10-12')).toBe(0) // Monday
    expect(weekdayOf('2026-10-18')).toBe(6) // Sunday
    expect(isWeekendNight('2026-10-16')).toBe(true) // Friday
    expect(isWeekendNight('2026-10-17')).toBe(true) // Saturday
    expect(isWeekendNight('2026-10-18')).toBe(false)
  })

  it('lists the years a half-open range touches', () => {
    expect(yearsBetween('2026-10-01', '2026-10-31')).toEqual([2026])
    expect(yearsBetween('2026-12-20', '2027-01-03')).toEqual([2026, 2027])
    expect(yearsBetween('2026-12-20', '2027-01-01')).toEqual([2026])
  })
})
