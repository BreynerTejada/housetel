import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { CancellationPolicy } from '../api'
import PoliciesPage from '../pages/PoliciesPage'
import { page } from './fixtures'

const FLEXIBLE: CancellationPolicy = {
  id: 'pol-flex',
  name: { es: 'Flexible 48h', en: 'Flexible 48h' },
  non_refundable: false,
  free_until_hours_before: 48,
  penalty_type: 'first_night',
  penalty_value: '0.00',
  description: { es: 'Gratis hasta 48 horas antes.', en: '' },
  plans_count: 2,
}

const NON_REFUNDABLE: CancellationPolicy = {
  ...FLEXIBLE,
  id: 'pol-nr',
  name: { es: 'No reembolsable', en: 'Non-refundable' },
  non_refundable: true,
  free_until_hours_before: 0,
  penalty_type: 'full',
  plans_count: 1,
}

function mockPolicies() {
  const posts: unknown[] = []
  server.use(
    http.get('/api/v1/rates/cancellation-policies/', () => HttpResponse.json(page([FLEXIBLE, NON_REFUNDABLE]))),
    http.post('/api/v1/rates/cancellation-policies/', async ({ request }) => {
      const body = await request.json()
      posts.push(body)
      return HttpResponse.json({ ...(body as object), id: 'pol-new', plans_count: 0 }, { status: 201 })
    }),
  )
  return posts
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('cancellation policies', () => {
  it('lists each policy with its free window, penalty and plans', async () => {
    mockPolicies()
    renderWithProviders(<PoliciesPage />)

    const flexible = (await screen.findByText('Flexible 48h')).closest('tr')!
    expect(within(flexible).getByText('Gratis hasta 48 h antes de la llegada')).toBeInTheDocument()
    expect(within(flexible).getByText('Primera noche')).toBeInTheDocument()
    expect(within(flexible).getByText('2 planes')).toBeInTheDocument()
    const nonRefundable = screen.getByText('No reembolsable', { selector: 'td *, td' }).closest('tr')!
    expect(within(nonRefundable).getByText('Sin reembolso')).toBeInTheDocument()
  })

  it('creates a policy with a percentage penalty', async () => {
    const posts = mockPolicies()
    const { user } = renderWithProviders(<PoliciesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nueva política' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva política' })
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Flexible 24h')
    await user.type(within(dialog).getByLabelText('Nombre en inglés'), 'Flexible 24h')
    await user.clear(within(dialog).getByLabelText('Cancelación gratis hasta (horas antes)'))
    await user.type(within(dialog).getByLabelText('Cancelación gratis hasta (horas antes)'), '24')
    await user.click(within(dialog).getByRole('combobox', { name: 'Penalidad' }))
    await user.click(await screen.findByRole('option', { name: 'Porcentaje del total' }))
    await user.type(within(dialog).getByLabelText('Porcentaje de penalidad'), '50')
    await user.type(within(dialog).getByLabelText('Descripción en español'), 'Gratis hasta 24 horas antes.')
    await user.click(within(dialog).getByRole('button', { name: 'Crear política' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({
      name: { es: 'Flexible 24h', en: 'Flexible 24h' },
      non_refundable: false,
      free_until_hours_before: 24,
      penalty_type: 'percent',
      penalty_value: '50',
      description: { es: 'Gratis hasta 24 horas antes.', en: '' },
    })
    expect(await screen.findByText('Política creada')).toBeInTheDocument()
  })

  it('a non-refundable policy charges the full stay and has no free window', async () => {
    const posts = mockPolicies()
    const { user } = renderWithProviders(<PoliciesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nueva política' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva política' })
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Tarifa especial')
    await user.click(within(dialog).getByRole('switch', { name: 'No reembolsable' }))
    expect(within(dialog).queryByLabelText('Cancelación gratis hasta (horas antes)')).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Crear política' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toMatchObject({ non_refundable: true, free_until_hours_before: 0, penalty_type: 'full' })
  })

  it('requires the Spanish name', async () => {
    const posts = mockPolicies()
    const { user } = renderWithProviders(<PoliciesPage />)

    await user.click(await screen.findByRole('button', { name: 'Nueva política' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva política' })
    await user.click(within(dialog).getByRole('button', { name: 'Crear política' }))

    expect(await within(dialog).findByText('Este campo es obligatorio')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
  })
})
