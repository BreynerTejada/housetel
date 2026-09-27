import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import PlansPage from '../pages/PlansPage'
import { mockPlansApi, PLAN_FLEX } from './fixtures'

function renderPage(route = '/app/rates/plans') {
  return renderWithProviders(<PlansPage />, { route, path: '/app/rates/plans' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('rate plans', () => {
  it('shows each base plan with the price its derived plans compute for every category', async () => {
    mockPlansApi()
    renderPage()

    const family = await screen.findByRole('table', { name: 'Precios de Tarifa flexible y sus planes derivados' })
    expect(within(family).getByRole('columnheader', { name: /No reembolsable.*−12 %/ })).toBeInTheDocument()
    expect(within(family).getByRole('columnheader', { name: /Con desayuno.*\+ \$\s35\.000/ })).toBeInTheDocument()

    const standard = within(family).getByRole('row', { name: /Estándar/ })
    const cells = within(standard).getAllByRole('cell').map((cell) => cell.textContent?.replace(/\s/g, ' '))
    expect(cells).toEqual(['$ 320.000', '$ 281.600', '$ 355.000'])

    const suite = within(family).getByRole('row', { name: /Suite Vista al Mar/ })
    expect(within(suite).getByText('Sin precio')).toBeInTheDocument()
    expect(within(suite).getByText('No lo vende')).toBeInTheDocument() // breakfast plan sells only Estándar
    const header = screen.getByRole('region', { name: /Tarifa flexible/ })
    expect(within(header).getAllByText('Flexible 48h').length).toBeGreaterThan(0)
  })

  it('creates a derived plan with its rule, categories, policy and channels', async () => {
    const writes = mockPlansApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Nuevo derivado de Tarifa flexible' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo plan' })
    expect(within(dialog).getByRole('radio', { name: 'Plan derivado' })).toBeChecked()
    await user.type(within(dialog).getByLabelText('Código'), 'VIP')
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Tarifa VIP')
    await user.type(within(dialog).getByLabelText('Nombre en inglés'), 'VIP rate')
    await user.click(within(dialog).getByRole('radio', { name: 'Monto por noche' }))
    await user.type(within(dialog).getByLabelText('Ajuste por noche'), '-20000')
    expect(within(dialog).getByText(/Estándar: \$\s320\.000 → \$\s300\.000/)).toBeInTheDocument()
    // a new derived plan sells every category of its base plan until one is unchecked
    expect(within(dialog).getByRole('checkbox', { name: 'Estándar' })).toBeChecked()
    await user.click(within(dialog).getByRole('checkbox', { name: 'Suite Vista al Mar' }))
    await user.click(within(dialog).getByRole('combobox', { name: 'Régimen de comidas' }))
    await user.click(await screen.findByRole('option', { name: 'Con desayuno' }))
    await user.click(within(dialog).getByRole('combobox', { name: 'Política de cancelación' }))
    await user.click(await screen.findByRole('option', { name: 'Flexible 48h' }))
    await user.click(within(dialog).getByRole('switch', { name: 'Todos los canales' }))
    await user.click(within(dialog).getByRole('checkbox', { name: 'Directo (recepción)' }))
    await user.click(within(dialog).getByRole('checkbox', { name: 'Booking engine' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear plan' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]).toEqual({
      method: 'POST',
      path: 'rate-plans',
      body: {
        code: 'VIP',
        name: { es: 'Tarifa VIP', en: 'VIP rate' },
        kind: 'derived',
        parent: 'plan-flex',
        derivation_type: 'amount',
        derivation_value: '-20000',
        room_types: ['rt-dbl'],
        meal_plan: 'breakfast',
        cancellation_policy: 'pol-flex',
        deposit_percent: '0',
        min_los_default: 1,
        is_public: true,
        channels: ['direct', 'booking_engine'],
        is_active: true,
      },
    })
    expect(await screen.findByText('Plan creado')).toBeInTheDocument()
  })

  it('creates a base plan that sells every category it checks', async () => {
    const writes = mockPlansApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Nuevo plan' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo plan' })
    expect(within(dialog).getByRole('radio', { name: 'Plan base' })).toBeChecked()
    expect(within(dialog).queryByLabelText('Ajuste por noche')).not.toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Código'), 'CORP')
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'Corporativa')
    expect(within(dialog).getByRole('checkbox', { name: 'Estándar' })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: 'Suite Vista al Mar' })).toBeChecked()
    await user.clear(within(dialog).getByLabelText('Estadía mínima por defecto'))
    await user.type(within(dialog).getByLabelText('Estadía mínima por defecto'), '2')
    await user.click(within(dialog).getByRole('switch', { name: 'Visible para huéspedes' }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear plan' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0].body).toMatchObject({
      code: 'CORP',
      name: { es: 'Corporativa', en: '' },
      kind: 'base',
      parent: null,
      derivation_type: 'percent',
      derivation_value: '0',
      room_types: ['rt-dbl', 'rt-ste'],
      min_los_default: 2,
      is_public: false,
      channels: [],
      cancellation_policy: null,
    })
  })

  it('checks the adjustment of a derived plan before sending it', async () => {
    const writes = mockPlansApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Nuevo derivado de Tarifa flexible' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nuevo plan' })
    await user.type(within(dialog).getByLabelText('Código'), 'X')
    await user.type(within(dialog).getByLabelText('Nombre en español'), 'X')
    await user.type(within(dialog).getByLabelText('Ajuste (%)'), '-120')
    await user.click(within(dialog).getByRole('button', { name: 'Crear plan' }))

    expect(await within(dialog).findByText('Un descuento no puede superar el 100 %.')).toBeInTheDocument()
    expect(writes).toHaveLength(0)
  })

  it('edits the rule of a derived plan', async () => {
    const writes = mockPlansApi()
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Editar No reembolsable' }))
    const dialog = await screen.findByRole('dialog', { name: 'Editar plan' })
    expect(within(dialog).queryByRole('radio', { name: 'Plan base' })).not.toBeInTheDocument() // the kind stays
    const adjustment = within(dialog).getByLabelText('Ajuste (%)')
    expect(adjustment).toHaveValue('-12')
    await user.clear(adjustment)
    await user.type(adjustment, '-15')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]).toMatchObject({ method: 'PATCH', path: 'rate-plans/plan-nr', body: { derivation_value: '-15' } })
    expect(await screen.findByText('Plan actualizado')).toBeInTheDocument()
  })

  it('invites to create the first plan when there is none', async () => {
    mockPlansApi({ plans: [] })
    renderPage()
    expect(await screen.findByText('Aún no hay planes tarifarios')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear plan base' })).toBeInTheDocument()
  })

  it('lets front desk read the plans without editing them', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['rates.view'], 'front_desk')] }))
    mockPlansApi()
    renderPage()

    await screen.findByRole('table', { name: /Precios de Tarifa flexible/ })
    expect(screen.queryByRole('button', { name: 'Nuevo plan' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Poner precio/ })).not.toBeInTheDocument()
  })
})

describe('tabs', () => {
  it('opens the tab named in the address', async () => {
    mockPlansApi({ plans: [PLAN_FLEX] })
    renderPage('/app/rates/plans?tab=seasons')
    expect(await screen.findByRole('tab', { name: 'Temporadas', selected: true })).toBeInTheDocument()
  })
})
