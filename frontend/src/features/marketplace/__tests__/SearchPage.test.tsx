import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { SearchResponse } from '../api'
import SearchPage from '../pages/SearchPage'
import { destinations, makeCard, makeSearch, PUBLIC } from './fixtures'

const STAY = 'checkin=2026-10-09&checkout=2026-10-11&adults=2'

const cheapest = {
  room_type: { id: 'rt', code: 'DBL', name: { es: 'Estándar', en: 'Standard' } },
  rate_plan: { id: 'rp', code: 'NR', name: { es: 'No reembolsable', en: 'Non-refundable' }, meal_plan: 'room_only' as const },
  total: '670208.00',
  per_night: '335104.00',
  currency: 'COP',
  available_units: 2,
  units_needed: 1,
  taxes_included: true,
}

const facets: SearchResponse['facets'] = {
  types: [
    { value: 'boutique', count: 1 },
    { value: 'hostel', count: 1 },
  ],
  stars: [
    { value: 4, count: 1 },
    { value: 2, count: 1 },
  ],
  amenities: [
    { code: 'wifi', name: { es: 'Wifi', en: 'Wi-Fi' }, icon: 'wifi', category: 'room', count: 2 },
    { code: 'pool', name: { es: 'Piscina', en: 'Pool' }, icon: 'waves-ladder', category: 'property', count: 1 },
  ],
}

/** Serves the search, answering from what the page asked for, and records every query. */
function serve(respond: (query: URLSearchParams) => SearchResponse) {
  const queries: URLSearchParams[] = []
  server.use(
    http.get(`${PUBLIC}/destinations/`, () => HttpResponse.json(destinations)),
    http.get(`${PUBLIC}/search/`, ({ request }) => {
      const query = new URL(request.url).searchParams
      queries.push(query)
      return HttpResponse.json(respond(query))
    }),
  )
  return queries
}

function renderSearch(route: string) {
  return renderWithProviders(<SearchPage />, { route, path: '/search', routes: [{ path: '/hotel/:slug', element: <p>hotel</p> }] })
}

describe('SearchPage', () => {
  it('shows the hotels of the destination with the cheapest price for the stay', async () => {
    const queries = serve(() =>
      makeSearch({ city: 'Cartagena', checkin: '2026-10-09', checkout: '2026-10-11', nights: 2, results: [makeCard({ offer: cheapest })], facets }),
    )
    renderSearch(`/search?city=Cartagena&${STAY}`)

    expect(screen.getByRole('heading', { level: 1, name: 'Cartagena' })).toBeInTheDocument()
    const card = (await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })).closest('article')!
    expect(within(card).getByText('$ 335.104')).toBeInTheDocument()
    expect(within(card).getByText('$ 670.208')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Ver disponibilidad' })).toHaveAttribute(
      'href',
      '/hotel/casa-aurora?checkin=2026-10-09&checkout=2026-10-11&adults=2',
    )
    expect(screen.getByText('1 alojamiento')).toBeInTheDocument()
    expect(Object.fromEntries(queries[0]!)).toEqual({
      city: 'Cartagena',
      checkin: '2026-10-09',
      checkout: '2026-10-11',
      adults: '2',
      children: '0',
      sort: 'recommended',
    })
  })

  it('filters with the facets of the destination and keeps the filters in the URL', async () => {
    const queries = serve((query) =>
      makeSearch({
        city: 'Cartagena',
        results: query.getAll('type').includes('hostel') ? [makeCard({ slug: 'hostal', name: 'Hostal del Mar', property_type: 'hostel' })] : [makeCard()],
        facets,
      }),
    )
    const { user, router } = renderSearch('/search?city=Cartagena&adults=2')

    await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })
    const types = screen.getAllByRole('group', { name: 'Tipo de alojamiento' })[0]!
    await user.click(within(types).getByRole('checkbox', { name: /Hostal/ }))

    expect(await screen.findByRole('heading', { name: 'Hostal del Mar' })).toBeInTheDocument()
    expect(new URLSearchParams(router.state.location.search).getAll('type')).toEqual(['hostel'])
    expect(queries.at(-1)!.getAll('type')).toEqual(['hostel'])

    const amenities = screen.getAllByRole('group', { name: 'Servicios' })[0]!
    await user.click(within(amenities).getByRole('checkbox', { name: /Piscina/ }))
    expect(new URLSearchParams(router.state.location.search).getAll('amenities')).toEqual(['pool'])
  })

  it('sorts by price', async () => {
    serve(() => makeSearch({ city: 'Cartagena', results: [makeCard({ offer: cheapest })], facets }))
    const { user, router } = renderSearch(`/search?city=Cartagena&${STAY}`)

    await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })
    await user.click(screen.getByRole('combobox', { name: 'Ordenar por' }))
    await user.click(await screen.findByRole('option', { name: 'Precio: menor a mayor' }))

    expect(new URLSearchParams(router.state.location.search).get('sort')).toBe('price')
  })

  it('suggests the destinations that have hotels when a city has none', async () => {
    serve(() => makeSearch({ city: 'Pasto', results: [], facets: { types: [], stars: [], amenities: [] } }))
    renderSearch('/search?city=Pasto&adults=2')

    expect(await screen.findByText('Todavía no hay alojamientos en Pasto')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Cartagena/ })).toHaveAttribute('href', '/search?city=Cartagena&adults=2')
  })

  it('offers to clear the filters when they leave no results', async () => {
    serve((query) => makeSearch({ city: 'Cartagena', results: query.getAll('stars').length ? [] : [makeCard()], facets }))
    const { user, router } = renderSearch('/search?city=Cartagena&adults=2&stars=2')

    expect(await screen.findByText('No hay alojamientos disponibles con esos criterios')).toBeInTheDocument()
    const results = screen.getByRole('region', { name: '0 alojamientos' })
    await user.click(within(results).getByRole('button', { name: 'Quitar filtros' }))

    expect(router.state.location.search).toBe('?city=Cartagena&adults=2')
    expect(await screen.findByRole('heading', { name: 'Hotel Casa Aurora' })).toBeInTheDocument()
  })
})
