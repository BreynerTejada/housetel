import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { BoundsPanel } from '../components/BoundsPanel'
import { BOUNDS, OPTIONS } from './fixtures'

interface Log {
  saved: unknown[]
  deleted: string[]
}

function mockBoundsApi(): Log {
  const log: Log = { saved: [], deleted: [] }
  let current = [...BOUNDS]
  server.use(
    http.get('/api/v1/revenue/options/', () => HttpResponse.json(OPTIONS)),
    http.get('/api/v1/revenue/bounds/', () => HttpResponse.json(current)),
    http.post('/api/v1/revenue/bounds/', async ({ request }) => {
      const body = (await request.json()) as { room_type: string; rate_plan: string; min_price: string | null; max_price: string | null }
      log.saved.push(body)
      const saved = { id: `bounds-${body.room_type}`, updated_at: '', ...body }
      current = [...current.filter((item) => item.room_type !== body.room_type), saved]
      return HttpResponse.json(saved, { status: 201 })
    }),
    http.delete('/api/v1/revenue/bounds/:id/', ({ params }) => {
      log.deleted.push(String(params.id))
      current = current.filter((item) => item.id !== params.id)
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return log
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('price bounds', () => {
  it('shows each category of each base plan with its default price and its bounds', async () => {
    mockBoundsApi()
    renderWithProviders(<BoundsPanel />)

    const table = await screen.findByRole('table', { name: 'Límites de precio' })
    const standard = within(table).getByRole('row', { name: /Estándar/ })
    expect(within(standard).getByLabelText('Precio mínimo de Estándar en Tarifa flexible')).toHaveValue('240.000')
    expect(within(standard).getByLabelText('Precio máximo de Estándar en Tarifa flexible')).toHaveValue('512.000')
    expect(within(standard).getByText('75 % del precio por defecto')).toBeInTheDocument()
    expect(within(standard).getByText('160 % del precio por defecto')).toBeInTheDocument()
    const suite = within(table).getByRole('row', { name: /Suite Vista al Mar/ })
    expect(within(suite).getByLabelText('Precio mínimo de Suite Vista al Mar en Tarifa flexible')).toHaveValue('')
  })

  it('saves the bounds of a category and plan', async () => {
    const log = mockBoundsApi()
    const { user } = renderWithProviders(<BoundsPanel />)

    const suite = await screen.findByRole('row', { name: /Suite Vista al Mar/ })
    const saveButton = await within(suite).findByRole('button', { name: 'Guardar los límites de Suite Vista al Mar en Tarifa flexible' })
    await user.type(within(suite).getByLabelText('Precio mínimo de Suite Vista al Mar en Tarifa flexible'), '500000')
    await user.click(saveButton)

    await waitFor(() => expect(log.saved).toHaveLength(1))
    expect(log.saved[0]).toEqual({ room_type: 'rt-ste', rate_plan: 'plan-flex', min_price: '500000', max_price: null })
    expect(await screen.findByText('Límites guardados')).toBeInTheDocument()
  })

  it('asks for a ceiling above the floor before saving', async () => {
    const log = mockBoundsApi()
    const { user } = renderWithProviders(<BoundsPanel />)

    const standard = await screen.findByRole('row', { name: /Estándar/ })
    const saveButton = await within(standard).findByRole('button', { name: 'Guardar los límites de Estándar en Tarifa flexible' })
    const max = within(standard).getByLabelText('Precio máximo de Estándar en Tarifa flexible')
    await user.clear(max)
    await user.type(max, '200000')
    await user.click(saveButton)

    expect(await within(standard).findByText('El máximo no puede ser menor que el mínimo')).toBeInTheDocument()
    expect(log.saved).toHaveLength(0)
  })

  it('removes the bounds of a category', async () => {
    const log = mockBoundsApi()
    const { user } = renderWithProviders(<BoundsPanel />)

    const standard = await screen.findByRole('row', { name: /Estándar/ })
    await user.click(await within(standard).findByRole('button', { name: 'Quitar los límites de Estándar en Tarifa flexible' }))
    await waitFor(() => expect(log.deleted).toEqual(['bounds-dbl']))
    // the row is drawn again from the server: empty bounds, nothing left to remove
    await waitFor(() =>
      expect(within(screen.getByRole('row', { name: /Estándar/ })).getByLabelText('Precio mínimo de Estándar en Tarifa flexible')).toHaveValue(''),
    )
    expect(screen.queryByRole('button', { name: 'Quitar los límites de Estándar en Tarifa flexible' })).not.toBeInTheDocument()
  })

  it('is read-only without revenue.manage', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['revenue.view'], 'front_desk')] }))
    mockBoundsApi()
    const { queryClient } = renderWithProviders(<BoundsPanel />)

    await waitFor(() => expect(queryClient.getQueryData(['me'])).toBeTruthy()) // permissions known
    const standard = await screen.findByRole('row', { name: /Estándar/ })
    expect(within(standard).getByLabelText('Precio mínimo de Estándar en Tarifa flexible')).toBeDisabled()
    expect(within(standard).queryByRole('button', { name: /Guardar/ })).not.toBeInTheDocument()
  })
})
