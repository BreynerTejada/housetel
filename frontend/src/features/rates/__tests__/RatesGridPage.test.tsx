import { QueryClient } from '@tanstack/react-query'
import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '@/lib/i18n'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RatesGridPage from '../pages/RatesGridPage'
import { makeGrid, mockGridApi } from './fixtures'

function renderPage() {
  return renderWithProviders(<RatesGridPage />, { route: '/app/rates' })
}

const priceCell = (name: RegExp) => screen.findByRole('button', { name })

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(makeMe())
})

describe('rates grid', () => {
  it('shows every category with its nightly prices, availability and where each price comes from', async () => {
    const { gridRequests } = mockGridApi()
    renderPage()

    const grid = await screen.findByRole('grid', { name: /Tarifa flexible/ })
    expect(within(grid).getByRole('rowheader', { name: /Estándar/ })).toBeInTheDocument()
    expect(within(grid).getByRole('rowheader', { name: /Suite Vista al Mar/ })).toBeInTheDocument()
    expect(await priceCell(/^Precio de Estándar el vie 25 sep: \$\s320\.000/)).toHaveAttribute('data-source', 'default')
    expect(await priceCell(/^Precio de Estándar el sáb 26 sep: \$\s368\.000/)).toHaveAttribute('data-source', 'season')
    expect(within(grid).getByRole('columnheader', { name: /dom 27.*Festivo de prueba/ })).toBeInTheDocument()
    expect(within(grid).getByText('Lleno')).toBeInTheDocument() // Estándar has 0 units on the 27th
    expect(screen.getByText('Temporada')).toBeInTheDocument() // legend
    // 14 nights from the business date, end exclusive
    expect(gridRequests[0].searchParams.get('start')).toBe('2026-09-25')
    expect(gridRequests[0].searchParams.get('end')).toBe('2026-10-09')
  })

  it('asks for the holiday names in the language on screen', async () => {
    const { gridRequests } = mockGridApi()
    renderPage()
    await screen.findByRole('grid', { name: /Tarifa flexible/ })
    expect(gridRequests.at(-1)?.searchParams.get('lang')).toBe('es')

    await act(() => i18n.changeLanguage('en'))
    await waitFor(() => expect(gridRequests.at(-1)?.searchParams.get('lang')).toBe('en'))
  })

  it('shows 14, 30, 60 or 90 nights and remembers the choice', async () => {
    const { gridRequests } = mockGridApi()
    const { user } = renderPage()

    const spans = await screen.findByRole('radiogroup', { name: 'Noches visibles' })
    expect(within(spans).getAllByRole('radio').map((radio) => radio.textContent)).toEqual([
      '14 noches',
      '30 noches',
      '60 noches',
      '90 noches',
    ])
    await user.click(within(spans).getByRole('radio', { name: '90 noches' }))

    await waitFor(() => expect(gridRequests.at(-1)?.searchParams.get('end')).toBe('2026-12-24'))
    expect(localStorage.getItem('housetel.rates.span')).toBe('90')
  })

  it('edits a price in its cell with the keyboard and saves only that night', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}')
    const input = screen.getByRole('textbox', { name: 'Nuevo precio de Estándar el vie 25 sep' })
    expect(input).toHaveValue('320.000')
    await user.keyboard('350000{Enter}')

    await waitFor(() => expect(bulkRequests).toHaveLength(1))
    expect(bulkRequests[0]).toEqual({
      room_type_ids: ['rt-dbl'],
      rate_plan_id: 'plan-flex',
      start: '2026-09-25',
      end: '2026-09-26',
      weekdays: [],
      set: { price: '350000' },
      source: 'manual',
    })
    const saved = await priceCell(/^Precio de Estándar el vie 25 sep: \$\s350\.000/)
    expect(saved).toHaveAttribute('data-source', 'manual')
    // Enter saves and goes down to the minimum stay of the same night
    expect(screen.getByRole('button', { name: /^Estadía mínima de Estándar el vie 25 sep/ })).toHaveFocus()
  })

  it('typing on a focused cell starts editing, and Tab saves and moves to the next night', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('34')
    expect(screen.getByRole('textbox', { name: /Nuevo precio/ })).toHaveValue('34')
    await user.keyboard('0000{Tab}')

    await waitFor(() => expect(bulkRequests).toHaveLength(1))
    expect(bulkRequests[0]).toMatchObject({ start: '2026-09-25', end: '2026-09-26', set: { price: '340000' } })
    expect(screen.getByRole('button', { name: /^Precio de Estándar el sáb 26 sep/ })).toHaveFocus()
  })

  it('moves with the arrow keys and discards an edit with Escape', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('button', { name: /^Precio de Estándar el sáb 26 sep/ })).toHaveFocus()
    await user.keyboard('{Enter}999{Escape}')

    expect(screen.queryByRole('textbox', { name: /Nuevo precio/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Precio de Estándar el sáb 26 sep: \$\s368\.000/ })).toHaveFocus()
    expect(bulkRequests).toHaveLength(0)
  })

  it('does not save a cell whose value did not change', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}{Enter}')
    expect(screen.getByRole('button', { name: /^Estadía mínima de Estándar el vie 25 sep/ })).toHaveFocus()
    await user.keyboard('{ArrowUp}{Enter}320000{Tab}')
    expect(screen.getByRole('button', { name: /^Precio de Estándar el sáb 26 sep/ })).toHaveFocus()
    expect(bulkRequests).toHaveLength(0)
  })

  it('edits the minimum stay and toggles restrictions in their rows', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: /^Estadía mínima de Suite Vista al Mar el sáb 26 sep/ }))
    await user.keyboard('2{Enter}')
    await waitFor(() => expect(bulkRequests).toHaveLength(1))
    expect(bulkRequests[0]).toMatchObject({ room_type_ids: ['rt-ste'], start: '2026-09-26', set: { min_los: 2 } })

    const arrival = screen.getByRole('button', { name: 'Cerrado a llegadas: Suite Vista al Mar, sáb 26 sep' })
    expect(arrival).toHaveAttribute('aria-pressed', 'false')
    await user.click(arrival)
    await waitFor(() => expect(bulkRequests).toHaveLength(2))
    expect(bulkRequests[1]).toMatchObject({ room_type_ids: ['rt-ste'], start: '2026-09-26', set: { cta: true } })
    expect(arrival).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: /^Estadía mínima de Estándar el dom 27 sep/ }))
    await user.keyboard('{Delete}')
    await waitFor(() => expect(bulkRequests).toHaveLength(3))
    expect(bulkRequests[2]).toMatchObject({ room_type_ids: ['rt-dbl'], start: '2026-09-27', set: { min_los: null } })
  })

  it('a price saved in the base plan reaches its derived plan without waiting for the cache', async () => {
    mockGridApi()
    // the app caches queries for 30 s (lib/query.ts); the default test client never does
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30_000, gcTime: Infinity } } })
    const { user } = renderWithProviders(<RatesGridPage />, { route: '/app/rates', queryClient })
    const choosePlan = async (name: RegExp) => {
      await user.click(await screen.findByRole('combobox', { name: 'Plan' }))
      await user.click(await screen.findByRole('option', { name }))
    }

    await choosePlan(/No reembolsable/) // its grid is now cached: 320.000 − 12 %
    expect(await priceCell(/^Precio de Estándar el vie 25 sep: \$\s281\.600/)).toBeInTheDocument()
    await choosePlan(/Tarifa flexible/)
    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep: \$\s320\.000/))
    await user.keyboard('{Enter}350000{Enter}')
    await priceCell(/^Precio de Estándar el vie 25 sep: \$\s350\.000/)

    await choosePlan(/No reembolsable/)
    expect(await priceCell(/^Precio de Estándar el vie 25 sep: \$\s308\.000/)).toBeInTheDocument() // 350.000 − 12 %
  })

  it('puts the price back and says why when saving fails', async () => {
    mockGridApi()
    server.use(
      http.post('/api/v1/rates/grid/bulk/', () =>
        HttpResponse.json({ detail: 'El precio no puede ser negativo', code: 'invalid_price' }, { status: 400 }),
      ),
    )
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}1{Enter}')

    expect(await screen.findByText('El precio no puede ser negativo')).toBeInTheDocument()
    expect(await priceCell(/^Precio de Estándar el vie 25 sep: \$\s320\.000/)).toHaveAttribute('data-source', 'default')
  })

  it('shows derived plans read-only and explains where their prices come from', async () => {
    const grid = makeGrid()
    mockGridApi({
      grid: {
        ...grid,
        rate_plan: { ...grid.rate_plan!, id: 'plan-nr', code: 'NR', kind: 'derived', parent: 'plan-flex', derivation_value: '-12.00', editable: false },
      },
    })
    const { user } = renderPage()

    expect(await screen.findByText(/se calcula desde Tarifa flexible/)).toBeInTheDocument()
    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}5')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edición masiva' })).not.toBeInTheDocument()
  })

  it('lets front desk read the grid without editing it', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['rates.view', 'bookings.view'], 'front_desk')] }))
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrado a llegadas: Estándar, vie 25 sep' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('button', { name: 'Edición masiva' })).not.toBeInTheDocument()
    expect(bulkRequests).toHaveLength(0)
  })
})

describe('undo of the last edit', () => {
  it('stays disabled while the control center cannot undo yet', async () => {
    mockGridApi()
    const { user } = renderPage()

    const undo = await screen.findByRole('button', { name: 'Deshacer' })
    expect(undo).toBeDisabled()
    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}350000{Enter}')
    await screen.findByRole('button', { name: /^Precio de Estándar el vie 25 sep: \$\s350\.000/ })

    await waitFor(() => expect(screen.getByText(/Deshacer estará disponible/)).toBeInTheDocument())
    expect(undo).toBeDisabled()
  })

  it('reverts the last edit through the generic audit undo when it is available', async () => {
    const { gridRequests } = mockGridApi()
    const undoRequests: unknown[] = []
    server.use(
      http.get('/api/v1/control/audit/:id/', ({ params }) =>
        HttpResponse.json({ id: params.id, reversible: true, undone_at: null }),
      ),
      http.post('/api/v1/control/audit/:id/undo/', async ({ params, request }) => {
        undoRequests.push({ id: params.id, body: await request.json() })
        return HttpResponse.json({ id: params.id })
      }),
    )
    const { user } = renderPage()

    await user.click(await priceCell(/^Precio de Estándar el vie 25 sep/))
    await user.keyboard('{Enter}350000{Enter}')
    const undo = screen.getByRole('button', { name: 'Deshacer' })
    await waitFor(() => expect(undo).toBeEnabled())
    const before = gridRequests.length
    await user.click(undo)

    await waitFor(() => expect(undoRequests).toEqual([{ id: 'evt-1', body: { confirm: true } }]))
    expect(await screen.findByText('Cambio deshecho')).toBeInTheDocument()
    await waitFor(() => expect(gridRequests.length).toBeGreaterThan(before))
    expect(undo).toBeDisabled()
  })
})
