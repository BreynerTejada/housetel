import { describe, expect, it } from 'vitest'
import { buildListParams, listStateSearch, parseListState, QUICK_VIEWS, quickViewParams } from '../lib/quickViews'

const BD = '2026-10-01'

describe('quickViewParams', () => {
  it('maps every quick view to the filters of GET /bookings/reservations/', () => {
    expect(quickViewParams('all', BD)).toEqual({})
    expect(quickViewParams('arrivals', BD)).toEqual({ arrival_from: BD, arrival_to: BD, status: ['confirmed', 'tentative'] })
    expect(quickViewParams('departures', BD)).toEqual({ departure_from: BD, departure_to: BD, status: ['checked_in'] })
    expect(quickViewParams('in_house', BD)).toEqual({ status: ['checked_in'] })
    expect(quickViewParams('unpaid', BD)).toEqual({ balance_due: '1' })
    expect(quickViewParams('unassigned', BD)).toEqual({ unassigned: '1' })
    expect(quickViewParams('tentative', BD)).toEqual({ status: ['tentative'] })
    expect(QUICK_VIEWS).toHaveLength(7)
  })
})

describe('buildListParams', () => {
  it('adds the search, source, page and order to the quick view', () => {
    const state = parseListState(new URLSearchParams('view=arrivals&q=gomez&source=phone&page=3&ordering=-balance'))

    expect(buildListParams(state, BD)).toEqual({
      arrival_from: BD,
      arrival_to: BD,
      status: ['confirmed', 'tentative'],
      q: 'gomez',
      source: 'phone',
      page: 3,
      page_size: 25,
      ordering: '-balance',
    })
  })

  it('only applies the status and arrival range filters to the full list', () => {
    const all = parseListState(new URLSearchParams('status=cancelled&from=2026-10-05&to=2026-10-09'))
    const inHouse = parseListState(new URLSearchParams('view=in_house&status=cancelled&from=2026-10-05'))

    expect(buildListParams(all, BD)).toMatchObject({
      status: ['cancelled'],
      arrival_from: '2026-10-05',
      arrival_to: '2026-10-09',
    })
    expect(buildListParams(inHouse, BD)).toEqual({ status: ['checked_in'], page: 1, page_size: 25 })
  })

  it('falls back to the full list for an unknown view', () => {
    expect(parseListState(new URLSearchParams('view=nope')).view).toBe('all')
  })
})

describe('listStateSearch', () => {
  it('writes a short URL: defaults left out, list-only filters only on the full list', () => {
    const full = parseListState(new URLSearchParams('status=cancelled&status=no_show&from=2026-10-05&q=ana&page=2&ordering=-balance'))
    const view = { ...parseListState(new URLSearchParams('view=arrivals&from=2026-10-05')), source: 'phone' }

    expect(listStateSearch(full).toString()).toBe('q=ana&status=cancelled&status=no_show&from=2026-10-05&page=2&ordering=-balance')
    expect(listStateSearch(view).toString()).toBe('view=arrivals&source=phone')
    expect(listStateSearch(parseListState(new URLSearchParams())).toString()).toBe('')
  })

  it('round-trips through parseListState', () => {
    const state = parseListState(new URLSearchParams('view=tentative&q=HT-7K&page=4'))

    expect(parseListState(listStateSearch(state))).toEqual(state)
  })
})

describe('page size', () => {
  it('keeps a page size the table offers and falls back to 25 for anything else', () => {
    expect(buildListParams(parseListState(new URLSearchParams('size=50')), BD)).toMatchObject({ page_size: 50 })
    expect(buildListParams(parseListState(new URLSearchParams('size=7')), BD)).toMatchObject({ page_size: 25 })
    expect(listStateSearch(parseListState(new URLSearchParams('size=100'))).toString()).toBe('size=100')
  })
})
