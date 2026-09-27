import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PromoCode } from '../api'
import PromosPage from '../pages/PromosPage'
import { FLEX, NR, page } from './fixtures'

const WELCOME: PromoCode = {
  id: 'promo-1',
  code: 'BIENVENIDA10',
  discount_type: 'percent',
  value: '10.00',
  valid_from: '2026-09-01',
  valid_to: '2026-12-31',
  stay_from: null,
  stay_to: null,
  rate_plans: [],
  max_uses: 100,
  uses: 3,
  is_active: true,
}

function mockPromos() {
  const posts: unknown[] = []
  server.use(
    http.get('/api/v1/rates/promo-codes/', () => HttpResponse.json(page([WELCOME]))),
    http.get('/api/v1/rates/rate-plans/', () => HttpResponse.json(page([FLEX, NR]))),
    http.post('/api/v1/rates/promo-codes/', async ({ request }) => {
      const body = await request.json()
      posts.push(body)
      return HttpResponse.json({ ...(body as object), id: 'promo-new', uses: 0 }, { status: 201 })
    }),
  )
  return posts
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('promo codes', () => {
  it('lists each code with its discount, windows, plans and uses', async () => {
    mockPromos()
    renderWithProviders(<PromosPage />)

    const row = (await screen.findByText('BIENVENIDA10')).closest('tr')!
    expect(within(row).getByText('10 %')).toBeInTheDocument()
    expect(within(row).getByText('1 sep – 31 dic 2026')).toBeInTheDocument()
    expect(within(row).getByText('Cualquier fecha')).toBeInTheDocument()
    expect(within(row).getByText('Todos los planes')).toBeInTheDocument()
    expect(within(row).getByText('3 de 100')).toBeInTheDocument()
  })

  it('creates a fixed discount per night limited to one plan', async () => {
    const posts = mockPromos()
    const { user } = renderWithProviders(<PromosPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo código' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo código' })
    await user.type(within(dialog).getByLabelText('Código'), 'verano')
    expect(within(dialog).getByLabelText('Código')).toHaveValue('VERANO')
    await user.click(within(dialog).getByRole('radio', { name: 'Monto por noche' }))
    await user.type(within(dialog).getByLabelText('Descuento por noche'), '50000')
    await user.click(await within(dialog).findByRole('checkbox', { name: 'No reembolsable' }))
    await user.type(within(dialog).getByLabelText('Máximo de usos'), '50')
    await user.click(within(dialog).getByRole('button', { name: 'Crear código' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({
      code: 'VERANO',
      discount_type: 'amount',
      value: '50000',
      valid_from: null,
      valid_to: null,
      stay_from: null,
      stay_to: null,
      rate_plans: ['plan-nr'],
      max_uses: 50,
      is_active: true,
    })
    expect(await screen.findByText('Código creado')).toBeInTheDocument()
  })

  it('checks the percentage before sending', async () => {
    const posts = mockPromos()
    const { user } = renderWithProviders(<PromosPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo código' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo código' })
    await user.type(within(dialog).getByLabelText('Código'), 'MITAD')
    await user.type(within(dialog).getByLabelText('Porcentaje de descuento'), '150')
    await user.click(within(dialog).getByRole('button', { name: 'Crear código' }))

    expect(await within(dialog).findByText('El porcentaje va de 1 a 100.')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
  })
})
