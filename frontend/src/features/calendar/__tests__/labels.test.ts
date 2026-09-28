import type { TFunction } from 'i18next'
import { describe, expect, it } from 'vitest'
import i18n from '@/lib/i18n'
import { compactPrice, indexRooms, invalidText, matchesSearch, signedMoney, sourceLabel, targetLabel } from '../lib/labels'
import { IDS, makeCalendar } from './fixtures'

const t = i18n.getFixedT('es') as TFunction

describe('compactPrice: prices that fit a day column', () => {
  it('shortens thousands and millions in the language on screen', () => {
    expect(compactPrice('320000.00', 'es')).toMatch(/^320\smil$/)
    expect(compactPrice('1250000.00', 'es')).toMatch(/^1,3\sM$/)
    expect(compactPrice('320000.00', 'en')).toBe('320K')
    expect(compactPrice('65000.00', 'en')).toBe('65K')
  })

  it('keeps one decimal below a hundred thousand, where rounding would hide real differences', () => {
    expect(compactPrice('57500.00', 'es')).toMatch(/^57,5\smil$/)
    expect(compactPrice('57500.00', 'en')).toBe('57.5K')
    expect(compactPrice('368400.00', 'es')).toMatch(/^368\smil$/)
    expect(compactPrice('900.00', 'es')).toBe('900')
  })

  it('shows nothing when there is no price', () => {
    expect(compactPrice(null, 'es')).toBe('')
  })
})

describe('matchesSearch', () => {
  it('finds a stay by guest name without accents or by booking code, ignoring case', () => {
    const stay = { guest_name: 'Sofía Mejía', code: 'HT-SOFIA5' }
    expect(matchesSearch(stay, 'sofia')).toBe(true)
    expect(matchesSearch(stay, ' MEJÍA ')).toBe(true)
    expect(matchesSearch(stay, 'ht-sof')).toBe(true)
    expect(matchesSearch(stay, 'laura')).toBe(false)
    expect(matchesSearch(stay, '   ')).toBe(false)
  })
})

describe('sourceLabel', () => {
  it('names the OTA when there is a channel, otherwise the source', () => {
    expect(sourceLabel(t, { source: 'ota', channel_code: 'booksim' })).toBe('BookSim')
    expect(sourceLabel(t, { source: 'ota', channel_code: 'expedia_x' })).toBe('expedia_x')
    expect(sourceLabel(t, { source: 'phone', channel_code: '' })).toBe('Teléfono')
  })
})

describe('targetLabel: where a moved stay would go, in words', () => {
  it('names beds, dorm rooms, rooms and the unassigned row of a category', () => {
    const index = indexRooms(makeCalendar())
    const at = (roomId: string | null, bedId: string | null, roomTypeId: string = IDS.dbl) =>
      targetLabel(t, 'es', index, { roomTypeId, roomId, bedId })
    expect(at(IDS.d1, IDS.bedB, IDS.dorm)).toBe('Cama B · D1')
    expect(at(IDS.d1, null, IDS.dorm)).toBe('Dormitorio D1')
    expect(at(IDS.r101, null)).toBe('Hab. 101')
    expect(at(null, null, IDS.ste)).toBe('Sin asignar · Suite Vista al Mar')
  })
})

describe('invalidText', () => {
  it('says who is in the way, or why the room is blocked', () => {
    expect(invalidText(t, { kind: 'invalid', reason: 'occupied', conflict: { type: 'stay', code: 'HT-MATEO2', guest: 'Mateo Ruiz' } })).toBe(
      'Ocupada por Mateo Ruiz (HT-MATEO2) en esas noches.',
    )
    expect(invalidText(t, { kind: 'invalid', reason: 'blocked', conflict: { type: 'block', kind: 'maintenance', reason: '' } })).toBe(
      'Bloqueada en esas noches: Mantenimiento.',
    )
    expect(invalidText(t, { kind: 'invalid', reason: 'past_arrival' })).toBe('La llegada no puede quedar antes de hoy.')
  })
})

describe('signedMoney', () => {
  it('writes differences with their sign', () => {
    expect(signedMoney('56800.00', 'COP')).toMatch(/^\+\$\s56\.800$/)
    expect(signedMoney('-12000.00', 'COP')).toMatch(/^−\$\s12\.000$/)
    expect(signedMoney('0.00', 'COP')).toMatch(/^\$\s0$/)
  })
})
