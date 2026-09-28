import { describe, expect, it } from 'vitest'
import { dayKey, groupByDay, insertAtCursor, listTime, windowHoursLeft } from '../lib/thread'

// Bogotá is UTC−5 all year: 2026-10-06T10:00:00-05:00 = 15:00 UTC.
const NOW = new Date('2026-10-06T15:00:00Z')

describe('windowHoursLeft (WhatsApp 24 h customer service window)', () => {
  it('counts whole hours left since the guest last wrote', () => {
    expect(windowHoursLeft('2026-10-06T14:20:00Z', NOW)).toBe(23) // 40 min ago → 23 h 20 min left
    expect(windowHoursLeft('2026-10-05T16:30:00Z', NOW)).toBe(1) // 22 h 30 min ago → 1 h 30 min left
  })

  it('is 0 in the last hour and null once it closed or the guest never wrote', () => {
    expect(windowHoursLeft('2026-10-05T15:30:00Z', NOW)).toBe(0) // 23 h 30 min ago
    expect(windowHoursLeft('2026-10-05T14:59:00Z', NOW)).toBeNull()
    expect(windowHoursLeft(null, NOW)).toBeNull()
  })
})

describe('listTime (conversation list)', () => {
  it('shows the clock today, "ayer" yesterday, the weekday this week and the date before', () => {
    expect(listTime('2026-10-06T13:05:00Z', 'es', NOW)).toBe('08:05')
    expect(listTime('2026-10-05T23:00:00Z', 'es', NOW)).toBe('ayer')
    expect(listTime('2026-10-05T23:00:00Z', 'en', NOW)).toBe('yesterday')
    expect(listTime('2026-10-02T18:00:00Z', 'es', NOW)).toBe('vie')
    expect(listTime('2026-09-20T18:00:00Z', 'es', NOW)).toBe('20 sep')
    expect(listTime('2026-09-20T18:00:00Z', 'en', NOW)).toBe('Sep 20')
    expect(listTime(null, 'es', NOW)).toBe('')
  })
})

describe('groupByDay (thread separators)', () => {
  it('groups consecutive messages by their local calendar day, oldest first', () => {
    const messages = [
      { id: 'a', created_at: '2026-10-05T02:00:00Z' }, // Oct 4, 21:00 in Bogotá
      { id: 'b', created_at: '2026-10-05T15:00:00Z' },
      { id: 'c', created_at: '2026-10-05T20:00:00Z' },
      { id: 'd', created_at: '2026-10-06T14:00:00Z' },
    ]
    expect(groupByDay(messages).map((group) => [group.day, group.items.map((m) => m.id)])).toEqual([
      ['2026-10-04', ['a']],
      ['2026-10-05', ['b', 'c']],
      ['2026-10-06', ['d']],
    ])
  })

  it('uses the local calendar day', () => {
    expect(dayKey('2026-10-06T04:59:00Z')).toBe('2026-10-05')
  })
})

describe('insertAtCursor', () => {
  it('replaces the selection and puts the caret after the insertion', () => {
    expect(insertAtCursor('Hola , bienvenida', '{{guest.first_name}}', 5, 5)).toEqual({
      text: 'Hola {{guest.first_name}}, bienvenida',
      caret: 25,
    })
    expect(insertAtCursor('Hola NOMBRE!', '{{guest.first_name}}', 5, 11)).toEqual({
      text: 'Hola {{guest.first_name}}!',
      caret: 25,
    })
  })

  it('appends when there is no caret yet', () => {
    expect(insertAtCursor('Hola', '{{nights}}', null, null)).toEqual({ text: 'Hola{{nights}}', caret: 14 })
  })
})
