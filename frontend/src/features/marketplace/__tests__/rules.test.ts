import { describe, expect, it } from 'vitest'
import { brandStyle, readableTextOn } from '../lib/brand'
import { buildIcs } from '../lib/ics'
import { placeFor, profileLayout, thermalFloor } from '../lib/places'
import { isForeignNonResident } from '../lib/tax'

describe('isForeignNonResident (IVA exemption, ET art. 481)', () => {
  it.each([
    ['US', 'US', true],
    ['FR', '', true], // a foreigner without a declared residence is a non-resident
    ['us', 'fr', true],
    ['US', 'CO', false], // lives in Colombia: pays IVA
    ['CO', 'US', false], // Colombians always pay IVA
    ['', 'US', false], // no nationality: never exempt
    [' ', ' ', false],
  ])('nationality %j + residence %j → %s', (nationality, residence, expected) => {
    expect(isForeignNonResident(nationality, residence)).toBe(expected)
  })
})

describe('buildIcs', () => {
  it('writes an all-day event from check-in to the (exclusive) check-out day', () => {
    const ics = buildIcs({
      code: 'HT-7K2M9Q',
      hotelName: 'Hotel Casa Aurora',
      address: 'Calle del Cuartel #36-77, Centro Histórico, Cartagena',
      checkin: '2026-10-15',
      checkout: '2026-10-17',
      description: 'Check-in desde las 15:00; check-out hasta las 12:00.',
      url: 'http://localhost:5173/g/abc',
      now: new Date('2026-10-01T14:05:09Z'),
    })

    expect(ics.split('\r\n')).toEqual([
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//Housetel//Reservas//ES',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'BEGIN:VEVENT',
      'UID:HT-7K2M9Q@housetel.co',
      'DTSTAMP:20261001T140509Z',
      'DTSTART;VALUE=DATE:20261015',
      'DTEND;VALUE=DATE:20261017',
      'SUMMARY:Hotel Casa Aurora · HT-7K2M9Q',
      'LOCATION:Calle del Cuartel #36-77\\, Centro Histórico\\, Cartagena',
      'DESCRIPTION:Check-in desde las 15:00\\; check-out hasta las 12:00.\\nhttp://l',
      ' ocalhost:5173/g/abc',
      'URL:http://localhost:5173/g/abc',
      'END:VEVENT',
      'END:VCALENDAR',
      '',
    ])
  })

  it('folds long lines at 75 octets without splitting a multi-byte character', () => {
    const ics = buildIcs({
      code: 'HT-AAAAAA',
      hotelName: 'Ñ'.repeat(60),
      address: '',
      checkin: '2026-10-15',
      checkout: '2026-10-16',
      description: '',
      url: '',
      now: new Date('2026-10-01T00:00:00Z'),
    })

    const lines = ics.split('\r\n')
    const encoder = new TextEncoder()
    expect(lines.every((line) => encoder.encode(line).length <= 75)).toBe(true)
    const summary = lines.filter((line) => line.startsWith('SUMMARY:') || line.startsWith(' ')).map((line, i) => (i ? line.slice(1) : line))
    expect(summary.join('')).toBe(`SUMMARY:${'Ñ'.repeat(60)} · HT-AAAAAA`)
    expect(ics).not.toContain('LOCATION:')
    expect(ics).not.toContain('URL:')
  })
})

describe('brand colors', () => {
  it('picks white or dark text by contrast', () => {
    expect(readableTextOn('#0E6E74')).toBe('#ffffff') // Aurora teal
    expect(readableTextOn('#3D5A80')).toBe('#ffffff')
    expect(readableTextOn('#F2C94C')).toBe('#1f1c19') // a yellow brand needs dark text
    expect(readableTextOn('#ffffff')).toBe('#1f1c19')
  })

  it('turns a hotel color into the accent variables of its pages', () => {
    expect(brandStyle('#0e6e74')).toEqual({
      '--brand': '#0E6E74',
      '--accent': '#0E6E74',
      '--accent-hover': 'color-mix(in srgb, #0E6E74 84%, #000)',
      '--accent-soft': 'color-mix(in srgb, #0E6E74 14%, var(--surface))',
      '--accent-ink': 'color-mix(in srgb, #0E6E74 72%, var(--text))',
      '--on-accent': '#ffffff',
      '--focus': 'color-mix(in srgb, #0E6E74 70%, transparent)',
    })
  })

  it('keeps the Housetel accent when the color is not a valid hex', () => {
    expect(brandStyle('')).toEqual({})
    expect(brandStyle('red')).toEqual({})
    expect(brandStyle('#12')).toEqual({})
  })
})

describe('places and thermal floors', () => {
  it('knows the altitude of the main destinations, with or without accents', () => {
    expect(placeFor('Bogotá')).toMatchObject({ altitude: 2640 })
    expect(placeFor('medellin')).toMatchObject({ altitude: 1495 })
    expect(placeFor('  CARTAGENA ')).toMatchObject({ altitude: 2 })
    expect(placeFor('Ciudad Inventada')).toBeNull()
  })

  it.each([
    [0, 'hot'],
    [999, 'hot'],
    [1000, 'temperate'],
    [1999, 'temperate'],
    [2000, 'cold'],
    [2999, 'cold'],
    [3000, 'paramo'],
  ])('%i m is the %s floor', (altitude, floor) => {
    expect(thermalFloor(altitude)).toBe(floor)
  })

  it('lays the destinations out from the sea to the highest one', () => {
    const layout = profileLayout([
      { city: 'Bogotá', altitude: 2640 },
      { city: 'Cartagena', altitude: 2 },
      { city: 'Medellín', altitude: 1495 },
    ])

    expect(layout.ceiling).toBe(3000)
    expect(layout.ticks).toEqual([0, 1000, 2000, 3000])
    expect(layout.points.map((point) => point.city)).toEqual(['Cartagena', 'Medellín', 'Bogotá'])
    // x at the center of each column, y as the share of the ceiling (0 = sea level)
    expect(layout.points.map((point) => [round(point.x), round(point.y)])).toEqual([
      [16.667, 0.067],
      [50, 49.833],
      [83.333, 88],
    ])
  })

  it('never makes a ceiling below 1.000 m', () => {
    expect(profileLayout([{ city: 'Santa Marta', altitude: 6 }]).ceiling).toBe(1000)
  })

  it('can keep a higher ceiling so every thermal floor stays in view', () => {
    const layout = profileLayout([{ city: 'Bogotá', altitude: 2640 }], { minCeiling: 4000 })

    expect(layout.ceiling).toBe(4000)
    expect(layout.ticks).toEqual([0, 1000, 2000, 3000, 4000])
    expect(layout.points[0]?.y).toBe(66)
  })
})

function round(value: number): number {
  return Math.round(value * 1000) / 1000
}
