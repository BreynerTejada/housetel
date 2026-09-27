import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RatesGridPage from '../pages/RatesGridPage'
import { mockGridApi } from './fixtures'

function renderPage() {
  return renderWithProviders(<RatesGridPage />, { route: '/app/rates' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(makeMe())
})

describe('bulk edit panel', () => {
  it('sends the chosen categories, nights, weekdays and changes in one request', async () => {
    const { bulkRequests, gridRequests } = mockGridApi()
    server.use(
      http.post('/api/v1/rates/grid/bulk/', async ({ request }) => {
        bulkRequests.push(await request.json())
        return HttpResponse.json({ updated: 4, audit_event_id: 'evt-bulk' })
      }),
    )
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edición masiva' }))
    const panel = await screen.findByRole('dialog', { name: 'Edición masiva' })
    const apply = within(panel).getByRole('button', { name: 'Aplicar cambios' })
    expect(apply).toBeDisabled() // nothing to change yet

    await user.click(within(panel).getByRole('checkbox', { name: 'Suite Vista al Mar' }))
    await user.click(within(panel).getByRole('button', { name: 'Fin de semana' }))
    await user.click(within(panel).getByRole('radio', { name: 'Subir o bajar un porcentaje' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Porcentaje' }), '10')
    await user.click(within(panel).getByRole('radio', { name: 'Fijar estadía mínima' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Noches de estadía mínima' }), '2')
    await user.click(within(within(panel).getByRole('radiogroup', { name: 'Venta cerrada' })).getByRole('radio', { name: 'Cerrar' }))

    // 25 Sep – 8 Oct: Friday and Saturday nights are 25, 26 Sep and 2, 3 Oct
    expect(within(panel).getByText('Cambia 4 noches en 1 categoría.')).toBeInTheDocument()
    await user.click(apply)

    await waitFor(() => expect(bulkRequests).toHaveLength(1))
    expect(bulkRequests[0]).toEqual({
      room_type_ids: ['rt-dbl'],
      rate_plan_id: 'plan-flex',
      start: '2026-09-25',
      end: '2026-10-09',
      weekdays: [4, 5],
      set: { price_delta_percent: '10', min_los: 2, stop_sell: true },
      source: 'bulk',
    })
    expect(await screen.findByText('Se actualizaron 4 noches')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edición masiva' })).not.toBeInTheDocument())
    await waitFor(() => expect(gridRequests.length).toBeGreaterThan(1)) // the grid is reloaded
  })

  it('opens from a category with only that category selected and sets an exact price', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edición masiva de Suite Vista al Mar' }))
    const panel = await screen.findByRole('dialog', { name: 'Edición masiva' })
    expect(within(panel).getByRole('checkbox', { name: 'Suite Vista al Mar' })).toBeChecked()
    expect(within(panel).getByRole('checkbox', { name: 'Estándar' })).not.toBeChecked()

    await user.click(within(panel).getByRole('radio', { name: 'Fijar un precio' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Precio por noche' }), '700000')
    await user.click(within(within(panel).getByRole('radiogroup', { name: 'Cerrado a llegadas' })).getByRole('radio', { name: 'Abrir' }))
    await user.click(within(panel).getByRole('button', { name: 'Aplicar cambios' }))

    await waitFor(() => expect(bulkRequests).toHaveLength(1))
    expect(bulkRequests[0]).toMatchObject({
      room_type_ids: ['rt-ste'],
      weekdays: [],
      set: { price: '700000', cta: false },
    })
  })

  it('keeps the panel open and shows why when the server rejects the change', async () => {
    mockGridApi()
    server.use(
      http.post('/api/v1/rates/grid/bulk/', () =>
        HttpResponse.json(
          { detail: 'El plan no vende alguna de las categorías', code: 'validation_error', fields: { room_type_ids: ['x'] } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edición masiva' }))
    const panel = await screen.findByRole('dialog', { name: 'Edición masiva' })
    await user.click(within(within(panel).getByRole('radiogroup', { name: 'Cerrado a salidas' })).getByRole('radio', { name: 'Cerrar' }))
    await user.click(within(panel).getByRole('button', { name: 'Aplicar cambios' }))

    expect(await within(panel).findByRole('alert')).toHaveTextContent('El plan no vende alguna de las categorías')
    expect(screen.getByRole('dialog', { name: 'Edición masiva' })).toBeInTheDocument()
  })

  it('does not silently drop a price or a stay that was chosen but not typed right', async () => {
    const { bulkRequests } = mockGridApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edición masiva' }))
    const panel = await screen.findByRole('dialog', { name: 'Edición masiva' })
    const apply = within(panel).getByRole('button', { name: 'Aplicar cambios' })
    await user.click(within(within(panel).getByRole('radiogroup', { name: 'Cerrado a llegadas' })).getByRole('radio', { name: 'Cerrar' }))
    await user.click(within(panel).getByRole('radio', { name: 'Fijar un precio' }))
    expect(apply).toBeDisabled()
    expect(within(panel).getByText('Escribe el nuevo precio o el ajuste.')).toBeInTheDocument()

    await user.type(within(panel).getByRole('textbox', { name: 'Precio por noche' }), '700000')
    expect(apply).toBeEnabled()

    await user.click(within(panel).getByRole('radio', { name: 'Fijar estadía mínima' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Noches de estadía mínima' }), '0')
    expect(apply).toBeDisabled()
    expect(within(panel).getByText('La estadía mínima y la máxima van de 1 a 365 noches.')).toBeInTheDocument()

    await user.click(within(panel).getByRole('radio', { name: 'Subir o bajar un porcentaje' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Porcentaje' }), '-120')
    await user.clear(within(panel).getByRole('textbox', { name: 'Noches de estadía mínima' }))
    await user.type(within(panel).getByRole('textbox', { name: 'Noches de estadía mínima' }), '2')
    expect(apply).toBeDisabled() // a price cannot go down more than 100 %
    expect(within(panel).getByText('Escribe el nuevo precio o el ajuste.')).toBeInTheDocument()
    expect(bulkRequests).toHaveLength(0)
  })

  it('needs at least one category', async () => {
    mockGridApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Edición masiva' }))
    const panel = await screen.findByRole('dialog', { name: 'Edición masiva' })
    await user.click(within(within(panel).getByRole('radiogroup', { name: 'Venta cerrada' })).getByRole('radio', { name: 'Cerrar' }))
    await user.click(within(panel).getByRole('checkbox', { name: 'Todas las categorías' }))
    expect(within(panel).getByRole('button', { name: 'Aplicar cambios' })).toBeDisabled()
    expect(within(panel).getByText('Elige al menos una categoría.')).toBeInTheDocument()
  })
})
