import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { QuoteResult } from '../api'
import RatesGridPage from '../pages/RatesGridPage'
import { mockGridApi, ROOM_TYPES } from './fixtures'

const SELLABLE: QuoteResult = {
  room_type_id: 'rt-dbl',
  rate_plan_id: 'plan-flex',
  checkin: '2026-09-25',
  checkout: '2026-09-27',
  adults: 3,
  children: 0,
  nights: [
    { date: '2026-09-25', base: '368000.00', extra_adults: '60000.00', extra_children: '0.00', discount: '42800.00', total: '385200.00' },
    { date: '2026-09-26', base: '368000.00', extra_adults: '60000.00', extra_children: '0.00', discount: '42800.00', total: '385200.00' },
  ],
  subtotal: '770400.00',
  discount_total: '85600.00',
  taxes: [{ code: 'IVA', name: 'IVA 19% alojamiento', rate: '19.00', amount: '146376.00', included: false, exempt: false }],
  tax_total: '146376.00',
  total: '916776.00',
  currency: 'COP',
  restrictions_ok: true,
  violations: [],
  promo_applied: 'BIENVENIDA10',
}

function mockQuote(result: QuoteResult) {
  const requests: unknown[] = []
  server.use(
    http.get('/api/v1/rates/room-types/', () => HttpResponse.json(ROOM_TYPES)),
    http.post('/api/v1/rates/quote/', async ({ request }) => {
      requests.push(await request.json())
      return HttpResponse.json(result)
    }),
  )
  return requests
}

function renderPage() {
  return renderWithProviders(<RatesGridPage />, { route: '/app/rates' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(makeMe())
})

describe('quote tester', () => {
  it('prices a stay night by night with the promo, taxes and total', async () => {
    mockGridApi()
    const requests = mockQuote(SELLABLE)
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Cotizar' }))
    const panel = await screen.findByRole('dialog', { name: 'Probar una cotización' })
    const adults = within(panel).getByLabelText('Adultos')
    await user.clear(adults)
    await user.type(adults, '3')
    await user.type(within(panel).getByLabelText('Código promocional'), 'bienvenida10')
    await user.click(within(panel).getByRole('button', { name: 'Calcular' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0]).toEqual({
      room_type_id: 'rt-dbl',
      rate_plan_id: 'plan-flex',
      checkin: '2026-09-25',
      checkout: '2026-09-27',
      adults: 3,
      children: 0,
      children_ages: [],
      promo_code: 'BIENVENIDA10',
      guest_is_foreign_non_resident: false,
    })
    expect(await within(panel).findByText('Se puede vender')).toBeInTheDocument()
    const nights = within(panel).getByRole('table', { name: 'Noches de la cotización' })
    expect(within(nights).getAllByRole('row')).toHaveLength(3) // header + 2 nights
    expect(within(panel).getByText(/Código BIENVENIDA10 aplicado/)).toBeInTheDocument()
    expect(within(panel).getByText('IVA 19% alojamiento (19 %)')).toBeInTheDocument()
    expect(within(panel).getByText(/^\$\s916\.776$/)).toBeInTheDocument()
    // the totals are a valid description list: every entry is a term with its value (screen readers pair them)
    const summary = within(panel).getByText('Total', { selector: 'dt' }).closest('dl')!
    for (const entry of Array.from(summary.children)) {
      expect(entry.tagName).toBe('DIV')
      expect(within(entry as HTMLElement).getByRole('term')).toBeInTheDocument()
      expect(within(entry as HTMLElement).getByRole('definition')).toBeInTheDocument()
    }
  })

  it('explains why a stay cannot be sold', async () => {
    mockGridApi()
    mockQuote({ ...SELLABLE, restrictions_ok: false, violations: ['min_los', 'promo_invalid'], promo_applied: null })
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Cotizar' }))
    const panel = await screen.findByRole('dialog', { name: 'Probar una cotización' })
    await user.click(within(panel).getByRole('button', { name: 'Calcular' }))

    expect(await within(panel).findByText('No se puede vender con estas condiciones')).toBeInTheDocument()
    expect(within(panel).getByText('La estadía es más corta que la estadía mínima de la noche de llegada.')).toBeInTheDocument()
    expect(within(panel).getByText('El código promocional no aplica a esta estadía (no bloquea la venta).')).toBeInTheDocument()
  })

  it('sends the ages of the children', async () => {
    mockGridApi()
    const requests = mockQuote(SELLABLE)
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Cotizar' }))
    const panel = await screen.findByRole('dialog', { name: 'Probar una cotización' })
    await user.type(within(panel).getByLabelText('Niños'), '2')
    await user.type(within(panel).getByLabelText('Edades de los niños'), '5, 13')
    await user.click(within(panel).getByRole('switch', { name: 'Extranjero no residente' }))
    await user.click(within(panel).getByRole('button', { name: 'Calcular' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0]).toMatchObject({ children: 2, children_ages: [5, 13], guest_is_foreign_non_resident: true })
  })

  it('is available to front desk, who can read rates', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['rates.view'], 'front_desk')] }))
    mockGridApi()
    mockQuote(SELLABLE)
    renderPage()
    expect(await screen.findByRole('button', { name: 'Cotizar' })).toBeInTheDocument()
  })
})
