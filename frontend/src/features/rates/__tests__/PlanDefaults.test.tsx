import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import PlansPage from '../pages/PlansPage'
import { mockPlansApi } from './fixtures'

function renderDefaults() {
  return renderWithProviders(<PlansPage />, { route: '/app/rates/plans?tab=defaults', path: '/app/rates/plans' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('default prices of the categories', () => {
  it('lists the default price, weekday adjustments and occupancy prices of every category of the plan', async () => {
    mockPlansApi()
    renderDefaults()

    const table = await screen.findByRole('table', { name: 'Precios por defecto de Tarifa flexible' })
    const standard = within(table).getByRole('row', { name: /Estándar/ })
    expect(within(standard).getByText(/^\$\s320\.000$/)).toBeInTheDocument()
    expect(within(standard).getByText('vie +15 % · sáb +15 %')).toBeInTheDocument()
    expect(within(standard).getByText(/^\$\s60\.000$/)).toBeInTheDocument()
    expect(within(standard).getByText(/^\$\s30\.000 · hasta 12 años$/)).toBeInTheDocument()

    const suite = within(table).getByRole('row', { name: /Suite Vista al Mar/ })
    expect(within(suite).getByText('Sin precio')).toBeInTheDocument()
  })

  it('prices a category that had no price, with its weekday adjustments', async () => {
    const writes = mockPlansApi()
    const { user } = renderDefaults()

    await user.click(await screen.findByRole('button', { name: 'Poner precio a Suite Vista al Mar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Precio por defecto · Suite Vista al Mar' })
    await user.type(within(dialog).getByLabelText('Precio por noche'), '650000')
    await user.click(within(dialog).getByRole('button', { name: 'Fin de semana +15 %' }))
    expect(within(dialog).getByLabelText('Viernes')).toHaveValue('15')
    expect(within(dialog).getByLabelText('Sábado')).toHaveValue('15')
    await user.type(within(dialog).getByLabelText('Domingo'), '-10')
    await user.type(within(dialog).getByLabelText('Adulto extra'), '80000')
    await user.type(within(dialog).getByLabelText('Una persona'), '550000')
    // 650.000 × 1,15 = 747.500 on Friday and Saturday; 650.000 × 0,9 = 585.000 on Sunday
    expect(within(dialog).getByText(/sáb \$\s747\.500/)).toBeInTheDocument()
    expect(within(dialog).getByText(/dom \$\s585\.000/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Guardar precio' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]).toEqual({
      method: 'POST',
      path: 'room-type-defaults',
      body: {
        room_type: 'rt-ste',
        rate_plan: 'plan-flex',
        price: '650000',
        dow_adjustments: { fri: 15, sat: 15, sun: -10 },
        extra_adult_price: '80000',
        extra_child_price: '0',
        child_age_limit: 12,
        single_occupancy_price: '550000',
      },
    })
    expect(await screen.findByText('Precio guardado')).toBeInTheDocument()
  })

  it('edits the default price of a category keeping what was not touched', async () => {
    const writes = mockPlansApi()
    const { user } = renderDefaults()

    await user.click(await screen.findByRole('button', { name: 'Editar precio de Estándar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Precio por defecto · Estándar' })
    const price = within(dialog).getByLabelText('Precio por noche')
    expect(price).toHaveValue('320.000')
    await user.clear(price)
    await user.type(price, '340000')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar precio' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0].body).toMatchObject({
      room_type: 'rt-dbl',
      rate_plan: 'plan-flex',
      price: '340000',
      dow_adjustments: { fri: 15, sat: 15 },
      extra_adult_price: '60000.00',
      single_occupancy_price: null,
    })
  })

  it('rejects weekday adjustments that are not percentages', async () => {
    const writes = mockPlansApi()
    const { user } = renderDefaults()

    await user.click(await screen.findByRole('button', { name: 'Editar precio de Estándar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Precio por defecto · Estándar' })
    await user.clear(within(dialog).getByLabelText('Lunes'))
    await user.type(within(dialog).getByLabelText('Lunes'), '-150')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar precio' }))

    expect(await within(dialog).findByText('Cada ajuste va de -100 % a 1000 %.')).toBeInTheDocument()
    expect(writes).toHaveLength(0)
  })
})
