import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import GuestsPage from '../pages/GuestsPage'
import { makeGuest, makeGuestSummary, page } from './fixtures'

const john = makeGuestSummary({
  id: 'guest-john',
  first_name: 'John',
  last_name: 'Smith',
  full_name: 'John Smith',
  email: 'john@example.com',
  phone: '+12125550123',
  document_type: 'PA',
  document_number: 'US123456',
  nationality: 'US',
  country_of_residence: 'US',
  is_foreign_non_resident: true,
  stays_count: 0,
  last_stay_date: null,
})

let requests: URLSearchParams[] = []

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: null, loggedOut: false })
  mockMe(makeMe())
  requests = []
  server.use(
    http.get('/api/v1/guests/guests/', ({ request }) => {
      requests.push(new URL(request.url).searchParams)
      return HttpResponse.json(page([makeGuestSummary({ is_vip: true }), john]))
    }),
    http.get('/api/v1/guests/guests/tags/', () => HttpResponse.json(['corporativo', 'frecuente'])),
    http.get('/api/v1/guests/guests/lookup/', () => HttpResponse.json([])),
  )
})

function renderPage() {
  return renderWithProviders(<GuestsPage />, {
    route: '/app/guests',
    path: '/app/guests',
    routes: [{ path: '/app/guests/:id', element: <p>perfil</p> }],
  })
}

describe('GuestsPage', () => {
  it('lists guests with their document, country and stays', async () => {
    renderPage()

    const ana = await screen.findByRole('row', { name: /Ana María Pérez Gómez/ })
    expect(within(ana).getByText('CC 52.123.456')).toBeInTheDocument()
    expect(within(ana).getByText('Colombia')).toBeInTheDocument()
    expect(within(ana).getByText('VIP')).toBeInTheDocument()
    const smith = screen.getByRole('row', { name: /John Smith/ })
    expect(within(smith).getByText('Estados Unidos')).toBeInTheDocument()
    expect(within(smith).getByText('Exento de IVA')).toBeInTheDocument()
  })

  it('searches and filters on the server', async () => {
    const { user } = renderPage()
    await screen.findByRole('row', { name: /John Smith/ })

    await user.type(screen.getByRole('searchbox', { name: 'Buscar por nombre, documento, correo o teléfono' }), 'perez')
    await waitFor(() => expect(requests.at(-1)?.get('q')).toBe('perez'))
    await user.click(screen.getByRole('button', { name: 'Solo VIP' }))

    await waitFor(() => expect(requests.at(-1)?.get('is_vip')).toBe('true'))
    expect(requests.at(-1)?.get('q')).toBe('perez')
    expect(screen.getByRole('button', { name: 'Solo VIP' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('says the list could not load and retries, instead of claiming there are no guests', async () => {
    let failing = true
    server.use(
      http.get('/api/v1/guests/guests/', () =>
        failing
          ? HttpResponse.json({ detail: 'El servidor no respondió', code: 'server_error' }, { status: 500 })
          : HttpResponse.json(page([john])),
      ),
    )
    const { user } = renderPage()

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('No pudimos cargar esta información')).toBeInTheDocument()
    expect(screen.queryByText(/Todavía no hay huéspedes/)).not.toBeInTheDocument()

    failing = false
    await user.click(within(alert).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('row', { name: /John Smith/ })).toBeInTheDocument()
  })

  it('opens the guest profile from a row', async () => {
    const { user, router } = renderPage()
    await user.click(await screen.findByRole('row', { name: /John Smith/ }))
    expect(router.state.location.pathname).toBe('/app/guests/guest-john')
  })

  it('creates a guest with the Habeas Data consent and opens it', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/guests/guests/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(makeGuest({ id: 'guest-new', full_name: 'Camila Rojas' }), { status: 201 })
      }),
    )
    const { user, router } = renderPage()
    await user.click(await screen.findByRole('button', { name: 'Nuevo huésped' }))

    const dialog = await screen.findByRole('dialog', { name: 'Nuevo huésped' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Nombres' }), 'Camila')
    await user.type(within(dialog).getByRole('textbox', { name: 'Apellidos' }), 'Rojas')
    await user.type(within(dialog).getByRole('textbox', { name: 'Número de documento' }), '52.123.456')
    await user.click(within(dialog).getByRole('checkbox', { name: 'Autorizó el tratamiento de sus datos personales' }))
    await user.click(within(dialog).getByRole('button', { name: 'Guardar huésped' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app/guests/guest-new'))
    expect(body).toMatchObject({
      first_name: 'Camila',
      last_name: 'Rojas',
      document_type: 'CC',
      document_number: '52.123.456',
      nationality: 'CO',
      data_processing_consent: true,
    })
  })

  it('points to the existing profile when the document is already registered', async () => {
    server.use(
      http.post('/api/v1/guests/guests/', () =>
        HttpResponse.json({ detail: 'Ya existe un huésped con ese documento', code: 'guest_exists', guest_id: 'guest-ana' }, { status: 409 }),
      ),
    )
    const { user, router } = renderPage()
    await user.click(await screen.findByRole('button', { name: 'Nuevo huésped' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo huésped' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Nombres' }), 'Ana')
    await user.type(within(dialog).getByRole('textbox', { name: 'Número de documento' }), '52123456')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar huésped' }))

    await user.click(await within(dialog).findByRole('button', { name: 'Abrir el perfil existente' }))
    expect(router.state.location.pathname).toBe('/app/guests/guest-ana')
  })
})
