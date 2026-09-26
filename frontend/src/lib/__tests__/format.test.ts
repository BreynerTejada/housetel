import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDateRange,
  formatMoney,
  formatNumber,
  formatPercent,
  formatRelative,
  nightsBetween,
  parseDate,
  toISODate,
} from '@/lib/format'

// ICU uses non-breaking spaces; compare with plain spaces so the intent stays readable.
const plain = (s: string) => s.replace(/\s/g, ' ')

describe('formatMoney', () => {
  it('formats COP API strings with Colombian separators and no decimals', () => {
    expect(plain(formatMoney('320000.00'))).toBe('$ 320.000')
  })

  it('rounds COP half up to whole pesos', () => {
    expect(plain(formatMoney('320000.50'))).toBe('$ 320.001')
    expect(plain(formatMoney('320000.49'))).toBe('$ 320.000')
  })

  it('accepts numbers', () => {
    expect(plain(formatMoney(1500))).toBe('$ 1.500')
  })

  it('keeps two decimals for currencies other than COP', () => {
    expect(plain(formatMoney('10.5', 'USD', 'en-US'))).toBe('$10.50')
  })

  it('renders a dash for missing or non-numeric values', () => {
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
    expect(formatMoney('')).toBe('—')
    expect(formatMoney('abc')).toBe('—')
  })
})

describe('formatDate', () => {
  it('treats YYYY-MM-DD as a calendar date, not UTC midnight', () => {
    // new Date('2026-10-12') would be Oct 11 at 19:00 in Bogotá.
    expect(formatDate('2026-10-12')).toBe('12 oct 2026')
  })

  it('uses an English default pattern for en', () => {
    expect(formatDate('2026-10-12', undefined, 'en')).toBe('Oct 12, 2026')
  })

  it('accepts a custom date-fns pattern', () => {
    expect(formatDate('2026-10-12', 'EEE d MMM', 'es')).toBe('lun 12 oct')
  })

  it('renders a dash for missing values', () => {
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatDateRange', () => {
  it('collapses a range inside one month', () => {
    expect(formatDateRange('2026-10-12', '2026-10-15')).toBe('12–15 oct 2026')
    expect(formatDateRange('2026-10-12', '2026-10-15', 'en')).toBe('Oct 12–15, 2026')
  })

  it('spells both months when the range crosses a month', () => {
    expect(formatDateRange('2026-10-30', '2026-11-02')).toBe('30 oct – 2 nov 2026')
    expect(formatDateRange('2026-10-30', '2026-11-02', 'en')).toBe('Oct 30 – Nov 2, 2026')
  })

  it('spells both years when the range crosses a year', () => {
    expect(formatDateRange('2026-12-30', '2027-01-02')).toBe('30 dic 2026 – 2 ene 2027')
  })

  it('shows a single day once', () => {
    expect(formatDateRange('2026-10-12', '2026-10-12')).toBe('12 oct 2026')
    expect(formatDateRange('2026-10-12', '2026-10-12', 'en')).toBe('Oct 12, 2026')
  })
})

describe('nightsBetween', () => {
  it('counts nights with an exclusive checkout', () => {
    expect(nightsBetween('2026-10-12', '2026-10-15')).toBe(3)
    expect(nightsBetween('2026-10-30', '2026-11-02')).toBe(3)
  })

  it('never returns negative nights', () => {
    expect(nightsBetween('2026-10-15', '2026-10-12')).toBe(0)
    expect(nightsBetween('2026-10-15', '2026-10-15')).toBe(0)
  })
})

describe('formatRelative', () => {
  const now = new Date('2026-09-25T12:00:00-05:00')

  it('describes past instants in Spanish by default', () => {
    expect(formatRelative('2026-09-25T11:55:00-05:00', 'es', now)).toBe('hace 5 minutos')
  })

  it('describes past instants in English', () => {
    expect(formatRelative('2026-09-25T11:55:00-05:00', 'en', now)).toBe('5 minutes ago')
  })
})

describe('parseDate and toISODate', () => {
  it('parses API dates at local midnight', () => {
    const d = parseDate('2026-10-12')
    expect(d?.getFullYear()).toBe(2026)
    expect(d?.getMonth()).toBe(9)
    expect(d?.getDate()).toBe(12)
    expect(d?.getHours()).toBe(0)
  })

  it('returns null for invalid input', () => {
    expect(parseDate('not-a-date')).toBeNull()
    expect(parseDate('')).toBeNull()
  })

  it('serializes the local calendar day for API payloads', () => {
    // 23:30 local is already the next day in UTC; the API must still get the local day.
    expect(toISODate(new Date(2026, 9, 12, 23, 30))).toBe('2026-10-12')
  })
})

describe('formatNumber and formatPercent', () => {
  it('uses Colombian grouping', () => {
    expect(formatNumber(1234567)).toBe('1.234.567')
  })

  it('formats percentage points with one decimal by default (es-CO has no space before %)', () => {
    expect(plain(formatPercent(72.5))).toBe('72,5%')
    expect(plain(formatPercent(72.5, 0))).toBe('73%')
    expect(plain(formatPercent(8, 0, 'en'))).toBe('8%')
  })
})
