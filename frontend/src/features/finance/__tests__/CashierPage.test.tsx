import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import CashierPage from '../pages/CashierPage'
import { makeShift } from './fixtures'

const SUMMARY = {
  date: '2026-09-25',
  currency: 'COP',
  payments: { count: 3, total: '570000.00' },
  refunds: { count: 1, total: '20000.00' },
  net_total: '550000.00',
  by_method: [
    { method: 'card_terminal', count: 1, total: '450000.00' },
    { method: 'cash', count: 2, total: '120000.00' },
  ],
  charges: { net: '600000.00', tax: '114000.00', total: '714000.00' },
}

function serve({ shift = null as ReturnType<typeof makeShift> | null } = {}) {
  server.use(
    http.get('/api/v1/finance/cash-shifts/current/', () => HttpResponse.json({ shift })),
    http.get('/api/v1/finance/summary/', () => HttpResponse.json(SUMMARY)),
    http.get('/api/v1/finance/cash-shifts/', () =>
      HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
    ),
  )
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

describe('CashierPage', () => {
  it('opens a shift with the float in the drawer', async () => {
    mockMe(makeMe())
    serve()
    let body: Record<string, unknown> | undefined
    server.use(
      http.post('/api/v1/finance/cash-shifts/open/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(makeShift(), { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<CashierPage />)

    const float = await screen.findByLabelText('Fondo inicial')
    await user.type(float, '200000')
    await user.click(screen.getByRole('button', { name: 'Abrir turno' }))

    await waitFor(() => expect(body).toEqual({ opening_float: '200000', notes: '' }))
  })

  it('shows the open shift, what came in and the day by method', async () => {
    mockMe(makeMe())
    serve({ shift: makeShift() })
    renderWithProviders(<CashierPage />)

    const expected = await screen.findByRole('group', { name: 'Efectivo esperado' })
    expect(within(expected).getByText('$ 300.000')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /HT-7K2M9Q/ })).toHaveTextContent('Camila Rodríguez')
    expect(screen.getByRole('button', { name: 'Cerrar turno' })).toBeInTheDocument()
    const day = screen.getByRole('region', { name: /Cobros del día/ })
    expect(await within(day).findByText('Datáfono')).toBeInTheDocument()
  })

  it('closes the shift counting the drawer by denomination', async () => {
    mockMe(makeMe())
    serve({ shift: makeShift() })
    let body: Record<string, unknown> | undefined
    server.use(
      http.post('/api/v1/finance/cash-shifts/shift-1/close/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(makeShift({ is_open: false, closed_at: '2026-09-25T15:00:00-05:00' }))
      }),
    )
    const { user } = renderWithProviders(<CashierPage />)

    await user.click(await screen.findByRole('button', { name: 'Cerrar turno' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cerrar turno' })
    await user.type(within(dialog).getByLabelText('Billetes de $ 100.000'), '2')
    await user.type(within(dialog).getByLabelText('Billetes de $ 50.000'), '1')
    expect(within(dialog).getByRole('status')).toHaveTextContent('Faltan $ 50.000')
    await user.type(within(dialog).getByLabelText('Billetes de $ 50.000'), '{backspace}2')
    expect(within(dialog).getByRole('status')).toHaveTextContent('Cuadra')
    await user.click(within(dialog).getByRole('button', { name: 'Cerrar turno' }))

    await waitFor(() => expect(body).toEqual({ denominations: { '100000': 2, '50000': 2 }, notes: '' }))
  })

  it('offers a retry when the shift history cannot be loaded', async () => {
    mockMe(makeMe())
    serve()
    server.use(
      http.get('/api/v1/finance/cash-shifts/', () =>
        HttpResponse.json({ detail: 'Error interno', code: 'server_error' }, { status: 500 }),
      ),
    )
    renderWithProviders(<CashierPage />)

    const history = await screen.findByRole('region', { name: 'Turnos anteriores' })
    expect(await within(history).findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(within(history).queryByText('Aún no hay turnos cerrados.')).not.toBeInTheDocument()
  })

  it('does not offer the cash drawer to people without the cashier permission', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['finance.view'], 'custom')] }))
    serve()
    renderWithProviders(<CashierPage />)

    expect(await screen.findByRole('region', { name: /Cobros del día/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir turno' })).not.toBeInTheDocument()
  })
})
