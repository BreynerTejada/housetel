import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SEARCH,
  parseSearch,
  parseStay,
  searchApiParams,
  searchParams,
  stayApiParams,
  stayParams,
} from '../lib/search-params'

const params = (query: string) => new URLSearchParams(query)

describe('parseStay', () => {
  it('reads dates, adults, children and their ages', () => {
    expect(parseStay(params('checkin=2026-10-15&checkout=2026-10-17&adults=3&children=2&ages=4,11'))).toEqual({
      checkin: '2026-10-15',
      checkout: '2026-10-17',
      adults: 3,
      children: 2,
      ages: [4, 11],
    })
  })

  it('defaults to two adults without dates', () => {
    expect(parseStay(params(''))).toEqual({ checkin: null, checkout: null, adults: 2, children: 0, ages: [] })
  })

  it.each([
    ['checkin=2026-10-17&checkout=2026-10-15', 'checkout before checkin'],
    ['checkin=2026-10-15&checkout=2026-10-15', 'zero nights'],
    ['checkin=2026-10-15', 'missing checkout'],
    ['checkin=15/10/2026&checkout=17/10/2026', 'not ISO dates'],
    ['checkin=2026-02-30&checkout=2026-03-02', 'impossible date'],
  ])('drops both dates when they are not a stay (%s: %s)', (query) => {
    const stay = parseStay(params(query))
    expect([stay.checkin, stay.checkout]).toEqual([null, null])
  })

  it('keeps guests inside the limits the API accepts', () => {
    expect(parseStay(params('adults=0')).adults).toBe(2)
    expect(parseStay(params('adults=abc')).adults).toBe(2)
    expect(parseStay(params('adults=40')).adults).toBe(2)
    expect(parseStay(params('children=-1')).children).toBe(0)
  })

  it('ignores ages that do not match the number of children or are out of range', () => {
    expect(parseStay(params('children=2&ages=4')).ages).toEqual([])
    expect(parseStay(params('children=1&ages=18')).ages).toEqual([])
    expect(parseStay(params('children=1&ages=x')).ages).toEqual([])
  })
})

describe('stay params', () => {
  it('writes only what the URL needs', () => {
    expect(stayParams({ checkin: null, checkout: null, adults: 2, children: 0, ages: [] })).toEqual({ adults: '2' })
    expect(stayParams({ checkin: '2026-10-15', checkout: '2026-10-17', adults: 1, children: 2, ages: [3, 9] })).toEqual({
      checkin: '2026-10-15',
      checkout: '2026-10-17',
      adults: '1',
      children: '2',
      ages: '3,9',
    })
  })

  it('sends the ages to the API as children_ages', () => {
    expect(stayApiParams({ checkin: '2026-10-15', checkout: '2026-10-17', adults: 2, children: 1, ages: [6] })).toEqual({
      checkin: '2026-10-15',
      checkout: '2026-10-17',
      adults: 2,
      children: 1,
      children_ages: '6',
    })
    expect(stayApiParams({ checkin: null, checkout: null, adults: 2, children: 1, ages: [] }).children_ages).toBeUndefined()
  })
})

describe('search state', () => {
  it('reads the city and every filter', () => {
    const state = parseSearch(
      params('city=Cartagena&checkin=2026-10-15&checkout=2026-10-17&adults=2&type=hotel&type=hostel&stars=4&amenities=pool&amenities=wifi&min_price=100000&max_price=400000&sort=price'),
    )

    expect(state).toEqual({
      ...DEFAULT_SEARCH,
      city: 'Cartagena',
      checkin: '2026-10-15',
      checkout: '2026-10-17',
      types: ['hotel', 'hostel'],
      stars: [4],
      amenities: ['pool', 'wifi'],
      minPrice: '100000',
      maxPrice: '400000',
      sort: 'price',
    })
  })

  it('drops unknown types, stars, prices and sorts', () => {
    const state = parseSearch(params('type=castle&stars=9&min_price=-5&max_price=abc&sort=cheap'))

    expect(state).toEqual(DEFAULT_SEARCH)
  })

  it('round-trips through the URL leaving defaults out', () => {
    const state = { ...DEFAULT_SEARCH, city: 'Medellín', types: ['hotel'], sort: 'stars' as const }

    const url = searchParams(state)

    expect(url.toString()).toBe('city=Medell%C3%ADn&adults=2&type=hotel&sort=stars')
    expect(parseSearch(url)).toEqual(state)
  })

  it('builds the API query with repeated list keys', () => {
    const query = searchApiParams({
      ...DEFAULT_SEARCH,
      city: 'Bogotá',
      checkin: '2026-10-15',
      checkout: '2026-10-16',
      stars: [3, 4],
      maxPrice: '250000',
    })

    expect(query).toEqual({
      city: 'Bogotá',
      checkin: '2026-10-15',
      checkout: '2026-10-16',
      adults: 2,
      children: 0,
      children_ages: undefined,
      type: [],
      stars: ['3', '4'],
      amenities: [],
      min_price: undefined,
      max_price: '250000',
      sort: 'recommended',
    })
  })
})
