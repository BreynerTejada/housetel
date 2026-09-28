import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import ReservationsPage from '../pages/ReservationsPage'
import { deskMe, FRONT_DESK, makeListItem, page } from './fixtures'

const LIST = '/api/v1/bookings/reservations/'

function serveList(results = [makeListItem(), makeListItem({ id: 'res-2', code: 'HT-TENT01', status: 'tentative', booker: { ...makeListItem().booker, id: 'guest-2', full_name: 'Ana Ruiz', is_vip: true }, balance: '0.00' })]) {
  const requests: URLSearchParams[] = []
  server.use(
    http.get(LIST, ({ request }) => {
      requests.push(new URL(request.url).searchParams)
      return HttpResponse.json(page(results))
    }),
  )
  return requests
}

const params = (search: URLSearchParams) => ({ ...Object.fromEntries(search), status: search.getAll('status') })

function renderPage(route = '/app/reservations') {
  return renderWithProviders(<ReservationsPage />, {
    route,
    path: '/app/reservations',
    routes: [
      { path: '/app/reservations/:id', element: <p>detalle</p> },
      { path: '/app/reservations/new', element: <p>asistente</p> },
    ],
  })
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(deskMe(FRONT_DESK))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReservationsPage', () => {
  it('lists the reservations of the hotel with their state and balance', async () => {
    const requests = serveList()
    renderPage()

    const table = await screen.findByRole('table', { name: 'Reservas' })
    const row = await within(table).findByRole('row', { name: /HT-7K2M9Q/ })
    expect(within(row).getByText('Valeria Mejía')).toBeInTheDocument()
    expect(within(row).getByText('Confirmada')).toBeInTheDocument()
    expect(within(row).getAllByText('$ 761.600')).toHaveLength(2)
    const tentative = within(table).getByRole('row', { name: /HT-TENT01/ })
    expect(within(tentative).getByText('Tentativa')).toBeInTheDocument()
    expect(params(requests[0]!)).toEqual({ page: '1', page_size: '25', status: [] })
  })

  it('quick views filter by the business date and stay in the URL', async () => {
    const requests = serveList()
    const { user, router } = renderPage()

    await screen.findByRole('row', { name: /HT-7K2M9Q/ })
    await user.click(screen.getByRole('radio', { name: 'Llegadas hoy' }))

    await waitFor(() =>
      expect(params(requests.at(-1)!)).toEqual({
        arrival_from: '2026-10-01',
        arrival_to: '2026-10-01',
        status: ['confirmed', 'tentative'],
        page: '1',
        page_size: '25',
      }),
    )
    expect(router.state.location.search).toBe('?view=arrivals')
  })

  it('opens on the view the link asks for', async () => {
    const requests = serveList()
    renderPage('/app/reservations?view=in_house')

    await screen.findByRole('row', { name: /HT-7K2M9Q/ })
    expect(params(requests[0]!)).toMatchObject({ status: ['checked_in'] })
    expect(screen.getByRole('radio', { name: 'En casa' })).toBeChecked()
  })

  it('searches by code, name, email or phone', async () => {
    const requests = serveList()
    const { user, router } = renderPage()

    await screen.findByRole('row', { name: /HT-7K2M9Q/ })
    await user.type(screen.getByRole('searchbox', { name: /Buscar por código/ }), 'gomez')

    await waitFor(() => expect(requests.at(-1)!.get('q')).toBe('gomez'))
    expect(router.state.location.search).toBe('?q=gomez')
  })

  it('opens a reservation from its row', async () => {
    serveList()
    const { user, router } = renderPage()

    await user.click(await screen.findByRole('row', { name: /HT-7K2M9Q/ }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app/reservations/res-1'))
  })

  it('exports the filtered list as CSV', async () => {
    serveList()
    let exported: URLSearchParams | undefined
    server.use(
      http.get('/api/v1/frontdesk/reservations/export/', ({ request }) => {
        exported = new URL(request.url).searchParams
        return new HttpResponse('Código;Estado\n', { headers: { 'Content-Type': 'text/csv; charset=utf-8' } })
      }),
    )
    const createObjectURL = vi.fn((blob: Blob) => (blob ? 'blob:reservas' : ''))
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { user } = renderPage('/app/reservations?view=unpaid')

    await screen.findByRole('row', { name: /HT-7K2M9Q/ })
    await user.click(screen.getByRole('button', { name: 'Exportar CSV' }))

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1))
    expect(Object.fromEntries(exported!)).toEqual({ balance_due: '1', lang: 'es' })
  })
})
