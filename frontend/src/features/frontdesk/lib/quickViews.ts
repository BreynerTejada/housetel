import type { Query } from '@/lib/api'

/**
 * Quick views of the reservations list (plan C1) and the list state kept in the URL
 * (`/app/reservations?view=arrivals&q=gomez&page=2`). Each view maps to the filters of
 * `GET /api/v1/bookings/reservations/` (docs/integration-notes/B2b-bookings.md › "Vistas rápidas de C1");
 * dates are the property's business date.
 */
export type QuickView = 'all' | 'arrivals' | 'departures' | 'in_house' | 'unpaid' | 'unassigned' | 'tentative'

export const QUICK_VIEWS: QuickView[] = ['all', 'arrivals', 'departures', 'in_house', 'unpaid', 'unassigned', 'tentative']

export const PAGE_SIZE = 25
export const PAGE_SIZES = [10, 25, 50, 100]

export interface ListState {
  view: QuickView
  q: string
  /** Status filter; only applies to the full list (the other views fix their own). */
  status: string[]
  source: string
  /** Arrival range (inclusive), only for the full list. */
  from: string
  to: string
  page: number
  pageSize: number
  ordering: string
}

export function isQuickView(value: string | null | undefined): value is QuickView {
  return QUICK_VIEWS.includes(value as QuickView)
}

export function quickViewParams(view: QuickView, bd: string): Query {
  switch (view) {
    case 'arrivals':
      return { arrival_from: bd, arrival_to: bd, status: ['confirmed', 'tentative'] }
    case 'departures':
      return { departure_from: bd, departure_to: bd, status: ['checked_in'] }
    case 'in_house':
      return { status: ['checked_in'] }
    case 'unpaid':
      return { balance_due: '1' }
    case 'unassigned':
      return { unassigned: '1' }
    case 'tentative':
      return { status: ['tentative'] }
    case 'all':
      return {}
  }
}

export function parseListState(search: URLSearchParams): ListState {
  const view = search.get('view')
  const page = Number(search.get('page'))
  const size = Number(search.get('size'))
  return {
    view: isQuickView(view) ? view : 'all',
    q: search.get('q') ?? '',
    status: search.getAll('status'),
    source: search.get('source') ?? '',
    from: search.get('from') ?? '',
    to: search.get('to') ?? '',
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: PAGE_SIZES.includes(size) ? size : PAGE_SIZE,
    ordering: search.get('ordering') ?? '',
  }
}

/** The URL of a list state (defaults are left out so links stay short). */
export function listStateSearch(state: ListState): URLSearchParams {
  const search = new URLSearchParams()
  if (state.view !== 'all') search.set('view', state.view)
  if (state.q) search.set('q', state.q)
  if (state.view === 'all') {
    state.status.forEach((status) => search.append('status', status))
    if (state.from) search.set('from', state.from)
    if (state.to) search.set('to', state.to)
  }
  if (state.source) search.set('source', state.source)
  if (state.page > 1) search.set('page', String(state.page))
  if (state.pageSize !== PAGE_SIZE) search.set('size', String(state.pageSize))
  if (state.ordering) search.set('ordering', state.ordering)
  return search
}

export function buildListParams(state: ListState, bd: string): Query {
  const params: Query = { ...quickViewParams(state.view, bd) }
  if (state.view === 'all') {
    if (state.status.length) params.status = state.status
    if (state.from) params.arrival_from = state.from
    if (state.to) params.arrival_to = state.to
  }
  if (state.q.trim()) params.q = state.q.trim()
  if (state.source) params.source = state.source
  params.page = state.page
  params.page_size = state.pageSize
  if (state.ordering) params.ordering = state.ordering
  return params
}
