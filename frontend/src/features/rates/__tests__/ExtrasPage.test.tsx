import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { Extra, Tax } from '../api'
import ExtrasPage from '../pages/ExtrasPage'
import { page } from './fixtures'

const TAXES: Tax[] = [
  {
    id: 'tax-room',
    code: 'IVA',
    name: 'IVA 19% alojamiento',
    rate: '19.00',
    applies_to: 'room',
    included_in_price: false,
    exempt_foreign_non_residents: true,
    is_active: true,
  },
  {
    id: 'tax-extras',
    code: 'IVA-EXTRAS',
    name: 'IVA 19% extras',
    rate: '19.00',
    applies_to: 'extras',
    included_in_price: false,
    exempt_foreign_non_residents: false,
    is_active: true,
  },
]

const BREAKFAST: Extra = {
  id: 'extra-breakfast',
  code: 'BREAKFAST',
  name: { es: 'Desayuno', en: 'Breakfast' },
  price: '35000.00',
  charge_type: 'per_person_night',
  tax: 'tax-extras',
  sellable_online: true,
  is_active: true,
}

function mockExtras() {
  const posts: unknown[] = []
  server.use(
    http.get('/api/v1/rates/extras/', () => HttpResponse.json(page([BREAKFAST]))),
    http.get('/api/v1/rates/taxes/', () => HttpResponse.json(page(TAXES))),
    http.post('/api/v1/rates/extras/', async ({ request }) => {
      const body = await request.json()
      posts.push(body)
      return HttpResponse.json({ ...(body as object), id: 'extra-new' }, { status: 201 })
    }),
  )
  return posts
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('extras', () => {
  it('lists each extra with its price, how it is charged and its tax', async () => {
    mockExtras()
    renderWithProviders(<ExtrasPage />)

    const row = (await screen.findByText('Desayuno')).closest('tr')!
    expect(within(row).getByText(/\$\s35\.000/)).toBeInTheDocument()
    expect(within(row).getByText('Por persona por noche')).toBeInTheDocument()
    expect(await within(row).findByText('IVA 19% extras')).toBeInTheDocument()
    expect(within(row).getByText('Venta en línea')).toBeInTheDocument()
  })

  it('creates an extra charged per night with the extras tax', async () => {
    const posts = mockExtras()
    const { user } = renderWithProviders(<ExtrasPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo extra' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo extra' })
    await user.type(within(dialog).getByLabelText('Código'), 'PARKING')
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Parqueadero')
    await user.type(within(dialog).getByLabelText('Nombre en inglés'), 'Parking')
    await user.type(within(dialog).getByLabelText('Precio'), '25000')
    await user.click(within(dialog).getByRole('combobox', { name: 'Cómo se cobra' }))
    await user.click(await screen.findByRole('option', { name: 'Por noche' }))
    await user.click(within(dialog).getByRole('combobox', { name: 'Impuesto' }))
    expect(screen.queryByRole('option', { name: 'IVA 19% alojamiento' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('option', { name: 'IVA 19% extras' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear extra' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({
      code: 'PARKING',
      name: { es: 'Parqueadero', en: 'Parking' },
      price: '25000',
      charge_type: 'per_night',
      tax: 'tax-extras',
      sellable_online: true,
      is_active: true,
    })
    expect(await screen.findByText('Extra creado')).toBeInTheDocument()
  })

  it('an extra can have no tax and needs a price', async () => {
    const posts = mockExtras()
    const { user } = renderWithProviders(<ExtrasPage />)

    await user.click(await screen.findByRole('button', { name: 'Nuevo extra' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo extra' })
    await user.type(within(dialog).getByLabelText('Código'), 'TOWEL')
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Toalla de playa')
    await user.click(within(dialog).getByRole('button', { name: 'Crear extra' }))
    expect(await within(dialog).findByText('Este campo es obligatorio')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText('Precio'), '10000')
    await user.click(within(dialog).getByRole('combobox', { name: 'Impuesto' }))
    await user.click(await screen.findByRole('option', { name: 'Sin impuesto' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear extra' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toMatchObject({ code: 'TOWEL', price: '10000', tax: null, charge_type: 'per_stay' })
  })
})
