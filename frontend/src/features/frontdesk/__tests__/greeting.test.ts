import { describe, expect, it } from 'vitest'
import { firstName, partOfDay } from '../lib/greeting'

describe('partOfDay', () => {
  it('reads the hour in the hotel timezone, not the browser one', () => {
    // 11:59 and 12:00 in Bogotá (UTC-5)
    expect(partOfDay(new Date('2026-10-01T16:59:00Z'), 'America/Bogota')).toBe('morning')
    expect(partOfDay(new Date('2026-10-01T17:00:00Z'), 'America/Bogota')).toBe('afternoon')
    expect(partOfDay(new Date('2026-10-01T23:59:00Z'), 'America/Bogota')).toBe('afternoon')
    expect(partOfDay(new Date('2026-10-02T00:00:00Z'), 'America/Bogota')).toBe('evening')
    expect(partOfDay(new Date('2026-10-01T09:59:00Z'), 'America/Bogota')).toBe('evening')
    expect(partOfDay(new Date('2026-10-01T10:00:00Z'), 'America/Bogota')).toBe('morning')
  })
})

describe('firstName', () => {
  it('is the first word of the full name, or nothing', () => {
    expect(firstName('Andrés Gómez')).toBe('Andrés')
    expect(firstName('  ')).toBe('')
  })
})
