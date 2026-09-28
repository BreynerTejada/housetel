import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { EmbedSnippet, EngineSettings, ListingSettings } from '../api'
import BookingEngineSettingsPage from '../pages/BookingEngineSettingsPage'
import { FLEX, NR } from './fixtures'

const STAFF = '/api/v1/marketplace'

function engine(overrides: Partial<EngineSettings> = {}): EngineSettings {
  return {
    enabled: true,
    primary_color: '#0E6E74',
    logo: '',
    logo_is_custom: false,
    hero_image: null,
    headline: { es: 'Una casa colonial dentro de la muralla' },
    show_promo_field: true,
    allowed_rate_plans: [],
    min_advance_hours: 0,
    max_advance_days: 365,
    terms: {},
    rate_plans: [
      { id: FLEX, code: 'FLEX', name: { es: 'Tarifa flexible' }, kind: 'base', channels: [], sells_on_engine: true },
      { id: NR, code: 'NR', name: { es: 'No reembolsable' }, kind: 'derived', channels: ['marketplace'], sells_on_engine: false },
    ],
    public_url: 'http://localhost:5173/h/casa-aurora',
    embed_url: 'http://localhost:5173/embed/casa-aurora',
    property: { name: 'Hotel Casa Aurora', slug: 'casa-aurora', city: 'Cartagena' },
    ...overrides,
  }
}

function listing(overrides: Partial<ListingSettings> = {}): ListingSettings {
  return {
    marketplace_listed: false,
    tagline: {},
    highlights: [],
    neighborhood: '',
    featured_photo_ids: [],
    photos: [
      { id: 'ph-a', url: '/media/a.jpg', caption: {}, room_type: null },
      { id: 'ph-b', url: '/media/b.jpg', caption: {}, room_type: { id: 'rt', code: 'STE', name: { es: 'Suite' } } },
    ],
    description: { es: 'Casa colonial del siglo XVII.' },
    name: 'Hotel Casa Aurora',
    city: 'Cartagena',
    star_rating: 4,
    property_type: 'boutique',
    public_url: 'http://localhost:5173/hotel/casa-aurora',
    ...overrides,
  }
}

const snippet: EmbedSnippet = {
  engine_url: 'http://localhost:5173/h/casa-aurora',
  embed_url: 'http://localhost:5173/embed/casa-aurora',
  iframe: '<iframe src="http://localhost:5173/embed/casa-aurora" title="Reservas · Hotel Casa Aurora"></iframe>',
  button: '<a href="http://localhost:5173/h/casa-aurora">Reservar ahora</a>',
}

function serve() {
  const patches: { engine: Record<string, unknown>[]; listing: Record<string, unknown>[] } = { engine: [], listing: [] }
  let currentEngine = engine()
  let currentListing = listing()
  server.use(
    http.get(`${STAFF}/booking-engine/`, () => HttpResponse.json(currentEngine)),
    http.patch(`${STAFF}/booking-engine/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.engine.push(body)
      currentEngine = { ...currentEngine, ...body } as EngineSettings
      return HttpResponse.json(currentEngine)
    }),
    http.get(`${STAFF}/listing/`, () => HttpResponse.json(currentListing)),
    http.patch(`${STAFF}/listing/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.listing.push(body)
      currentListing = { ...currentListing, ...body } as ListingSettings
      return HttpResponse.json(currentListing)
    }),
    http.get(`${STAFF}/embed-snippet/`, () => HttpResponse.json(snippet)),
    http.get('/api/v1/rates/promo-codes/', () =>
      HttpResponse.json({
        count: 1,
        next: null,
        previous: null,
        results: [{ id: 'p1', code: 'BIENVENIDA10', discount_type: 'percent', value: '10.00', valid_from: null, valid_to: null, stay_from: null, stay_to: null, is_active: true }],
      }),
    ),
  )
  return patches
}

function renderPage() {
  return renderWithProviders(<BookingEngineSettingsPage />, { route: '/app/settings/booking-engine', path: '/app/settings/booking-engine' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: 'prop-1', loggedOut: false })
})

describe('BookingEngineSettingsPage', () => {
  it('saves only what changed in the booking engine and previews the brand live', async () => {
    const patches = serve()
    const { user } = renderPage()

    const color = await screen.findByLabelText('Código del color')
    await user.clear(color)
    await user.type(color, '#8A4F7D')
    const preview = screen.getByRole('figure', { name: 'Vista previa' })
    expect(preview.style.getPropertyValue('--accent')).toBe('#8A4F7D')
    expect(screen.getByText(/Texto sobre este color: 6[,.]\d:1 · se lee bien/)).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /Tarifa flexible/ }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(patches.engine).toHaveLength(1))
    expect(patches.engine[0]).toEqual({ primary_color: '#8A4F7D', allowed_rate_plans: [FLEX] })
    expect(await screen.findByText('Cambios guardados')).toBeInTheDocument()
  })

  it('warns when the brand color is hard to read', async () => {
    serve()
    const { user } = renderPage()

    const color = await screen.findByLabelText('Código del color')
    await user.clear(color)
    await user.type(color, '#F2C94C')

    expect(screen.getByText(/poco contraste/)).toBeInTheDocument()
  })

  it('lists the hotel in the marketplace with its featured photos in order', async () => {
    const patches = serve()
    const { user } = renderPage()

    await user.click(await screen.findByRole('tab', { name: 'Marketplace' }))
    await user.click(await screen.findByRole('switch', { name: 'Aparecer en el marketplace de Housetel' }))
    await user.type(screen.getByLabelText('Barrio o sector'), 'Centro Histórico')
    const photos = screen.getByRole('group', { name: 'Fotos destacadas' })
    await user.click(within(photos).getAllByRole('button', { name: 'Destacar esta foto' })[1]!)
    await user.click(within(photos).getAllByRole('button', { name: 'Destacar esta foto' })[0]!)
    expect(within(photos).getByText('1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(patches.listing).toHaveLength(1))
    expect(patches.listing[0]).toEqual({ marketplace_listed: true, neighborhood: 'Centro Histórico', featured_photo_ids: ['ph-b', 'ph-a'] })
  })

  it('gives the snippet to paste on the hotel website', async () => {
    serve()
    const { user } = renderPage()

    await user.click(await screen.findByRole('tab', { name: 'En tu web' }))
    const iframeBlock = await screen.findByRole('group', { name: 'Widget para tu web' })
    await user.click(within(iframeBlock).getByRole('button', { name: 'Copiar' }))

    // user-event installs a clipboard: what the button copied can be read back
    expect(await navigator.clipboard.readText()).toBe(snippet.iframe)
    expect(await screen.findByText('BIENVENIDA10')).toBeInTheDocument()
  })
})
