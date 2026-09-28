/**
 * In Colombia the climate is decided by altitude ("pisos térmicos"): the same week can mean 30 °C on the
 * Caribbean coast and 14 °C in Bogotá. The marketplace tells guests where each destination sits.
 */

export type ThermalFloor = 'hot' | 'temperate' | 'cold' | 'paramo'

export interface Place {
  name: string
  department: string
  /** Meters above sea level (urban center). */
  altitude: number
}

const PLACES: Place[] = [
  { name: 'San Andrés', department: 'San Andrés y Providencia', altitude: 1 },
  { name: 'Cartagena', department: 'Bolívar', altitude: 2 },
  { name: 'Riohacha', department: 'La Guajira', altitude: 5 },
  { name: 'Santa Marta', department: 'Magdalena', altitude: 6 },
  { name: 'Barranquilla', department: 'Atlántico', altitude: 18 },
  { name: 'Mompox', department: 'Bolívar', altitude: 33 },
  { name: 'Leticia', department: 'Amazonas', altitude: 96 },
  { name: 'Cúcuta', department: 'Norte de Santander', altitude: 320 },
  { name: 'Neiva', department: 'Huila', altitude: 442 },
  { name: 'Villavicencio', department: 'Meta', altitude: 467 },
  { name: 'Santa Fe de Antioquia', department: 'Antioquia', altitude: 550 },
  { name: 'Minca', department: 'Magdalena', altitude: 650 },
  { name: 'Bucaramanga', department: 'Santander', altitude: 959 },
  { name: 'Cali', department: 'Valle del Cauca', altitude: 1018 },
  { name: 'San Gil', department: 'Santander', altitude: 1117 },
  { name: 'Barichara', department: 'Santander', altitude: 1336 },
  { name: 'Pereira', department: 'Risaralda', altitude: 1411 },
  { name: 'Medellín', department: 'Antioquia', altitude: 1495 },
  { name: 'Armenia', department: 'Quindío', altitude: 1551 },
  { name: 'Jardín', department: 'Antioquia', altitude: 1750 },
  { name: 'Popayán', department: 'Cauca', altitude: 1760 },
  { name: 'Salento', department: 'Quindío', altitude: 1895 },
  { name: 'Guatapé', department: 'Antioquia', altitude: 1925 },
  { name: 'Villa de Leyva', department: 'Boyacá', altitude: 2149 },
  { name: 'Manizales', department: 'Caldas', altitude: 2160 },
  { name: 'Pasto', department: 'Nariño', altitude: 2527 },
  { name: 'Bogotá', department: 'Cundinamarca', altitude: 2640 },
  { name: 'Zipaquirá', department: 'Cundinamarca', altitude: 2650 },
  { name: 'Tunja', department: 'Boyacá', altitude: 2782 },
]

const ALIASES: Record<string, string> = {
  'cartagena de indias': 'cartagena',
  'bogota d.c.': 'bogota',
  'bogota dc': 'bogota',
  'santa cruz de mompox': 'mompox',
  'san andres isla': 'san andres',
}

export function normalizePlace(value: string): string {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '').trim().replace(/\s+/g, ' ').toLowerCase()
}

const INDEX = new Map(PLACES.map((place) => [normalizePlace(place.name), place]))

/** The destination behind a city name (with or without accents), or null when we do not know it. */
export function placeFor(city: string | null | undefined): Place | null {
  if (!city) return null
  const key = normalizePlace(city)
  return INDEX.get(ALIASES[key] ?? key) ?? null
}

const LOWERCASE_WORDS = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'en'])

/**
 * The destination as a title: the canonical name when we know it («cartagena» → «Cartagena», «bogota» →
 * «Bogotá», also for the cities the API lists), otherwise the typed words capitalized («villa de leyva» →
 * «Villa de Leyva»).
 */
export function cityTitle(city: string, known: readonly string[] = []): string {
  const typed = city.trim().replace(/\s+/g, ' ')
  if (!typed) return ''
  const key = normalizePlace(typed)
  const listed = known.find((name) => normalizePlace(name) === key)
  if (listed) return listed
  const place = placeFor(typed)
  if (place) return place.name
  return typed
    .split(' ')
    .map((word, index) => {
      const lower = word.toLocaleLowerCase('es')
      if (index > 0 && LOWERCASE_WORDS.has(lower)) return lower
      return lower.charAt(0).toLocaleUpperCase('es') + lower.slice(1)
    })
    .join(' ')
}

/** Below 1.000 m hot, up to 2.000 m temperate, up to 3.000 m cold, above that páramo. */
export function thermalFloor(altitude: number): ThermalFloor {
  if (altitude < 1000) return 'hot'
  if (altitude < 2000) return 'temperate'
  if (altitude < 3000) return 'cold'
  return 'paramo'
}

export const THERMAL_FLOORS: { floor: ThermalFloor; from: number; to: number | null }[] = [
  { floor: 'hot', from: 0, to: 1000 },
  { floor: 'temperate', from: 1000, to: 2000 },
  { floor: 'cold', from: 2000, to: 3000 },
  { floor: 'paramo', from: 3000, to: null },
]

export interface ProfileLayout<T> {
  /** Top of the scale in meters: the next thousand above the highest destination (at least 1.000). */
  ceiling: number
  ticks: number[]
  /** Destinations from the sea up; `x` and `y` in percent (x at the center of each column, y = 0 at sea level). */
  points: (T & { x: number; y: number })[]
}

/**
 * Lays destinations out as an altitude profile, from the lowest to the highest. `minCeiling` keeps a taller
 * scale (e.g. 4.000 m so the páramo stays visible even when no destination reaches it).
 */
export function profileLayout<T extends { altitude: number }>(items: T[], { minCeiling = 1000 } = {}): ProfileLayout<T> {
  const sorted = [...items].sort((a, b) => a.altitude - b.altitude)
  const highest = sorted.at(-1)?.altitude ?? 0
  const ceiling = Math.max(minCeiling, Math.ceil(highest / 1000) * 1000)
  const ticks = Array.from({ length: ceiling / 1000 + 1 }, (_, index) => index * 1000)
  const points = sorted.map((item, index) => ({
    ...item,
    x: ((index + 0.5) / sorted.length) * 100,
    y: (Math.max(0, item.altitude) / ceiling) * 100,
  }))
  return { ceiling, ticks, points }
}
