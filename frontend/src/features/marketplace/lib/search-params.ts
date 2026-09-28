/**
 * Search and stay state lives in the URL (shareable, back button friendly). These helpers read it defensively
 * (anything the API would reject falls back to the default) and write only what differs from the defaults.
 */
import type { Query } from '@/lib/api'

export interface Stay {
  /** `YYYY-MM-DD` or null (both dates or none) */
  checkin: string | null
  checkout: string | null
  adults: number
  children: number
  /** One age per child (0–17), or empty when unknown. */
  ages: number[]
}

export const PROPERTY_TYPES = ['hotel', 'hostel', 'boutique', 'aparthotel', 'glamping'] as const
export type PropertyType = (typeof PROPERTY_TYPES)[number]
export const SORTS = ['recommended', 'price', '-price', 'stars'] as const
export type SearchSort = (typeof SORTS)[number]

export interface SearchState extends Stay {
  city: string
  types: string[]
  stars: number[]
  amenities: string[]
  /** Whole pesos as typed (price per night), or `''`. */
  minPrice: string
  maxPrice: string
  sort: SearchSort
}

export const MAX_ADULTS = 20
export const MAX_CHILDREN = 10
export const MAX_CHILD_AGE = 17

export const DEFAULT_STAY: Stay = { checkin: null, checkout: null, adults: 2, children: 0, ages: [] }

export const DEFAULT_SEARCH: SearchState = {
  ...DEFAULT_STAY,
  city: '',
  types: [],
  stars: [],
  amenities: [],
  minPrice: '',
  maxPrice: '',
  sort: 'recommended',
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** A real calendar day written as `YYYY-MM-DD` (2026-02-30 is not). */
export function isIsoDate(value: string | null | undefined): value is string {
  const match = value ? ISO_DATE.exec(value) : null
  if (!match) return false
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])]
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

function intInRange(raw: string | null, min: number, max: number): number | null {
  if (raw === null || !/^-?\d+$/.test(raw.trim())) return null
  const value = Number(raw)
  return value >= min && value <= max ? value : null
}

function parseAges(raw: string | null, children: number): number[] {
  if (!raw || children === 0) return []
  const parts = raw.split(',').map((part) => part.trim())
  const ages = parts.map((part) => intInRange(part, 0, MAX_CHILD_AGE))
  if (ages.length !== children || ages.some((age) => age === null)) return []
  return ages as number[]
}

export function parseStay(params: URLSearchParams): Stay {
  const checkin = params.get('checkin')
  const checkout = params.get('checkout')
  const validDates = isIsoDate(checkin) && isIsoDate(checkout) && checkout > checkin
  const children = intInRange(params.get('children'), 0, MAX_CHILDREN) ?? 0
  return {
    checkin: validDates ? checkin : null,
    checkout: validDates ? checkout : null,
    adults: intInRange(params.get('adults'), 1, MAX_ADULTS) ?? DEFAULT_STAY.adults,
    children,
    ages: parseAges(params.get('ages'), children),
  }
}

/** URL parameters of a stay: dates only when set, children and ages only when there are children. */
export function stayParams(stay: Stay): Record<string, string> {
  const params: Record<string, string> = {}
  if (stay.checkin && stay.checkout) {
    params.checkin = stay.checkin
    params.checkout = stay.checkout
  }
  params.adults = String(stay.adults)
  if (stay.children > 0) params.children = String(stay.children)
  if (stay.ages.length > 0) params.ages = stay.ages.join(',')
  return params
}

/** Query of the public API (`children_ages` as `4,7`). */
export function stayApiParams(stay: Stay) {
  return {
    checkin: stay.checkin,
    checkout: stay.checkout,
    adults: stay.adults,
    children: stay.children,
    children_ages: stay.ages.length > 0 ? stay.ages.join(',') : undefined,
  }
}

function priceParam(raw: string | null): string {
  return raw !== null && /^\d+$/.test(raw.trim()) ? String(Number(raw)) : ''
}

export function parseSearch(params: URLSearchParams): SearchState {
  const types = params.getAll('type').filter((type): type is PropertyType => (PROPERTY_TYPES as readonly string[]).includes(type))
  const stars = params
    .getAll('stars')
    .map((value) => intInRange(value, 1, 5))
    .filter((value): value is number => value !== null)
  const sort = params.get('sort')
  return {
    ...parseStay(params),
    city: (params.get('city') ?? '').trim(),
    types: [...new Set(types)],
    stars: [...new Set(stars)],
    amenities: [...new Set(params.getAll('amenities').filter(Boolean))],
    minPrice: priceParam(params.get('min_price')),
    maxPrice: priceParam(params.get('max_price')),
    sort: (SORTS as readonly string[]).includes(sort ?? '') ? (sort as SearchSort) : 'recommended',
  }
}

/** The search as URL parameters, leaving the defaults out. */
export function searchParams(state: SearchState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.city) params.set('city', state.city)
  for (const [key, value] of Object.entries(stayParams(state))) params.set(key, value)
  state.types.forEach((type) => params.append('type', type))
  state.stars.forEach((star) => params.append('stars', String(star)))
  state.amenities.forEach((code) => params.append('amenities', code))
  if (state.minPrice) params.set('min_price', state.minPrice)
  if (state.maxPrice) params.set('max_price', state.maxPrice)
  if (state.sort !== 'recommended') params.set('sort', state.sort)
  return params
}

/** Query of `GET /public/marketplace/search/` (list parameters repeat the key). */
export function searchApiParams(state: SearchState): Query {
  return {
    city: state.city,
    ...stayApiParams(state),
    type: state.types,
    stars: state.stars.map(String),
    amenities: state.amenities,
    min_price: state.minPrice || undefined,
    max_price: state.maxPrice || undefined,
    sort: state.sort,
  }
}

/** How many filters are on (the price range counts as one). */
export function activeFilterCount(state: SearchState): number {
  return state.types.length + state.stars.length + state.amenities.length + (state.minPrice || state.maxPrice ? 1 : 0)
}
