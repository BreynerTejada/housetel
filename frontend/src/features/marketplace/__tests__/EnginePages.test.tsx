import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { EngineConfig } from '../api'
import EmbedPage from '../pages/EmbedPage'
import EnginePage from '../pages/EnginePage'
import { DBL, FLEX, makeDetail, makeEngineConfig, makeOffer, makeOffers, PUBLIC } from './fixtures'

function serveEngine(config: EngineConfig = makeEngineConfig(), { detailStatus = 200 } = {}) {
  const detailVias: string[] = []
  const offerVias: string[] = []
  server.use(
    http.get(`${PUBLIC}/properties/casa-aurora/booking-engine/`, () => HttpResponse.json(config)),
    http.get(`${PUBLIC}/properties/casa-aurora/`, ({ request }) => {
      detailVias.push(new URL(request.url).searchParams.get('via') ?? '')
      return detailStatus === 200
        ? HttpResponse.json(makeDetail({ via: 'booking_engine', marketplace_listed: false }))
        : HttpResponse.json({ detail: 'Este hotel no recibe reservas en línea', code: 'booking_engine_disabled' }, { status: 404 })
    }),
    http.get(`${PUBLIC}/properties/casa-aurora/offers/`, ({ request }) => {
      offerVias.push(new URL(request.url).searchParams.get('via') ?? '')
      return HttpResponse.json(makeOffers([makeOffer(DBL, FLEX, '761600.00')]))
    }),
  )
  return { detailVias, offerVias }
}

afterEach(() => {
  document.documentElement.removeAttribute('style')
})

describe('EnginePage (/h/:slug)', () => {
  it("is the hotel's own page: its color, its name and its booking engine rates", async () => {
    const { detailVias, offerVias } = serveEngine()
    const { user } = renderWithProviders(<EnginePage />, {
      route: '/h/casa-aurora?checkin=2026-10-09&checkout=2026-10-11&adults=2',
      path: '/h/:slug',
      routes: [{ path: '/h/:slug/book', element: <p>checkout del hotel</p> }],
    })

    expect(await screen.findByRole('heading', { level: 1, name: 'Hotel Casa Aurora' })).toBeInTheDocument()
    expect(screen.getByText('Una casa colonial para despertar dentro de la muralla')).toBeInTheDocument()
    // the hotel color replaces the Housetel accent everywhere (portals included)
    expect(document.documentElement.style.getPropertyValue('--accent')).toBe('#0E6E74')
    expect(screen.getByText('Reservas directas con tecnología Housetel')).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Elegir Estándar, Tarifa flexible' }))
    const summary = screen.getByRole('complementary', { name: 'Tu selección' })
    expect(within(summary).getByRole('link', { name: 'Reservar' }).getAttribute('href')).toMatch(/^\/h\/casa-aurora\/book\?/)
    expect(detailVias).toEqual(['booking_engine'])
    expect(offerVias).toEqual(['booking_engine'])
  })

  it('says the hotel does not take online bookings when its engine is off', async () => {
    serveEngine(makeEngineConfig({ enabled: false }), { detailStatus: 404 })
    renderWithProviders(<EnginePage />, { route: '/h/casa-aurora', path: '/h/:slug' })

    expect(await screen.findByText('Este hotel no recibe reservas en línea por ahora')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '+57 605 660 1234' })).toHaveAttribute('href', 'tel:+576056601234')
  })
})

describe('EmbedPage (/embed/:slug)', () => {
  it('opens the hotel engine with the chosen stay in a new tab', async () => {
    serveEngine()
    renderWithProviders(<EmbedPage />, { route: '/embed/casa-aurora', path: '/embed/:slug' })

    const form = await screen.findByRole('search', { name: 'Reserva en Hotel Casa Aurora' })
    expect(form).toHaveAttribute('action', '/h/casa-aurora')
    expect(form).toHaveAttribute('target', '_blank')
    expect(within(form).getByLabelText('Llegada')).toHaveAttribute('name', 'checkin')
    expect(within(form).getByLabelText('Salida')).toHaveAttribute('name', 'checkout')
    expect(within(form).getByLabelText('Adultos')).toHaveAttribute('name', 'adults')
    expect(within(form).getByRole('button', { name: /Ver disponibilidad/ })).toBeInTheDocument()
  })

  it('does not open a stay whose check-out is not after the check-in', async () => {
    serveEngine()
    const { user } = renderWithProviders(<EmbedPage />, { route: '/embed/casa-aurora', path: '/embed/:slug' })

    const form = await screen.findByRole('search', { name: 'Reserva en Hotel Casa Aurora' })
    const checkin = within(form).getByLabelText('Llegada')
    const checkout = within(form).getByLabelText('Salida')
    await user.clear(checkin)
    await user.type(checkin, '2026-10-12')
    await user.clear(checkout)
    await user.type(checkout, '2026-10-10')
    await user.click(within(form).getByRole('button', { name: /Ver disponibilidad/ }))

    expect(screen.getByRole('alert')).toHaveTextContent('La salida debe ser después de la llegada.')
  })
})
