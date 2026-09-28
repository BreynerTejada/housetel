import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { OffersResponse, PropertyDetail } from '../api'
import HotelPage from '../pages/HotelPage'
import { DBL, FLEX, makeDetail, makeOffer, makeOffers, NR, PUBLIC, STE } from './fixtures'

const STAY = 'checkin=2026-10-09&checkout=2026-10-11&adults=2'

function serve({
  detail = makeDetail(),
  offers = () => HttpResponse.json(makeOffers(standardOffers())),
}: { detail?: PropertyDetail | null; offers?: (query: URLSearchParams) => Response } = {}) {
  const offerQueries: URLSearchParams[] = []
  server.use(
    http.get(`${PUBLIC}/properties/casa-aurora/`, () =>
      detail ? HttpResponse.json(detail) : HttpResponse.json({ detail: 'No disponible', code: 'not_found' }, { status: 404 }),
    ),
    http.get(`${PUBLIC}/properties/casa-aurora/offers/`, ({ request }) => {
      const query = new URL(request.url).searchParams
      offerQueries.push(query)
      return offers(query)
    }),
  )
  return offerQueries
}

function standardOffers() {
  return [makeOffer(DBL, NR, '670208.00'), makeOffer(DBL, FLEX, '761600.00'), makeOffer(STE, FLEX, '1547000.00', { available_units: 1, max_quantity: 1 })]
}

function renderHotel(route: string) {
  return renderWithProviders(<HotelPage />, {
    route,
    path: '/hotel/:slug',
    routes: [{ path: '/book/:slug', element: <p>checkout</p> }],
  })
}

describe('HotelPage', () => {
  it('shows the hotel and its rooms, and asks for dates before showing prices', async () => {
    const offerQueries = serve()
    renderHotel('/hotel/casa-aurora')

    expect(await screen.findByRole('heading', { level: 1, name: 'Hotel Casa Aurora' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Estándar' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Suite Vista al Mar' })).toBeInTheDocument()
    expect(screen.getByText('Elige tus fechas para ver precios y disponibilidad.')).toBeInTheDocument()
    expect(screen.getByText('Cancelación gratis hasta 2 días antes de la llegada')).toBeInTheDocument()
    expect(offerQueries).toHaveLength(0)
  })

  it('prices the rooms for the stay and takes the chosen ones to the checkout', async () => {
    const offerQueries = serve()
    const { user } = renderHotel(`/hotel/casa-aurora?${STAY}`)

    await user.click(await screen.findByRole('button', { name: 'Elegir Estándar, Tarifa flexible' }))
    await user.click(screen.getByRole('button', { name: 'Agregar Estándar, Tarifa flexible' }))
    await user.click(screen.getByRole('button', { name: 'Elegir Suite Vista al Mar, Tarifa flexible' }))

    const summary = screen.getByRole('complementary', { name: 'Tu selección' })
    expect(within(summary).getByText('2 × Estándar')).toBeInTheDocument()
    expect(within(summary).getByText('1 × Suite Vista al Mar')).toBeInTheDocument()
    // 2 × 761.600 + 1.547.000
    expect(within(summary).getByText('$ 3.070.200')).toBeInTheDocument()
    expect(within(summary).getByRole('link', { name: 'Reservar' })).toHaveAttribute(
      'href',
      `/book/casa-aurora?checkin=2026-10-09&checkout=2026-10-11&adults=2&items=${DBL}%3A${FLEX}%3A2%2C${STE}%3A${FLEX}%3A1`,
    )
    expect(Object.fromEntries(offerQueries[0]!)).toEqual({
      checkin: '2026-10-09',
      checkout: '2026-10-11',
      adults: '2',
      children: '0',
      via: 'marketplace',
    })
  })

  it('shares the rooms of a type between its rates', async () => {
    serve()
    const { user } = renderHotel(`/hotel/casa-aurora?${STAY}`)

    await user.click(await screen.findByRole('button', { name: 'Elegir Estándar, Tarifa flexible' }))
    await user.click(screen.getByRole('button', { name: 'Agregar Estándar, Tarifa flexible' }))

    // both standard rooms are taken by the flexible rate
    expect(screen.getByRole('button', { name: 'Elegir Estándar, No reembolsable' })).toBeDisabled()
  })

  it('applies a promo code and says whether it worked', async () => {
    const offerQueries = serve({
      offers: (query) => {
        const code = query.get('promo_code')
        const response: OffersResponse = makeOffers(standardOffers(), code ? { promo: { code: code.toUpperCase(), applied: true } } : {})
        return HttpResponse.json(response)
      },
    })
    const { user } = renderHotel(`/hotel/casa-aurora?${STAY}`)

    await screen.findByRole('button', { name: 'Elegir Estándar, Tarifa flexible' })
    await user.type(screen.getByRole('textbox', { name: 'Código promocional' }), 'bienvenida10')
    await user.click(screen.getByRole('button', { name: 'Ver disponibilidad' }))

    expect(await screen.findByText('Código BIENVENIDA10 aplicado')).toBeInTheDocument()
    expect(offerQueries.at(-1)!.get('promo_code')).toBe('BIENVENIDA10')
  })

  it('explains when the hotel does not sell those dates online', async () => {
    serve({
      offers: () =>
        HttpResponse.json(
          { detail: 'Este hotel no recibe reservas en línea para esa fecha de llegada', code: 'too_soon', earliest_checkin: '2026-10-03' },
          { status: 400 },
        ),
    })
    renderHotel(`/hotel/casa-aurora?${STAY}`)

    expect(await screen.findByText('Este hotel recibe reservas en línea con llegada desde el 3 oct 2026.')).toBeInTheDocument()
  })

  it('says so when the hotel is not on the marketplace', async () => {
    serve({ detail: null })
    renderHotel('/hotel/casa-aurora')

    expect(await screen.findByText('Este alojamiento no está disponible')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a la búsqueda' })).toHaveAttribute('href', '/search')
  })
})
