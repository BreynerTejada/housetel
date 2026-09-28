import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { RevenueSettings } from '../api'
import { SettingsPanel } from '../components/SettingsPanel'
import { SETTINGS } from './fixtures'

function mockSettingsApi(initial: RevenueSettings = SETTINGS) {
  const patches: Record<string, unknown>[] = []
  let current = { ...initial }
  server.use(
    http.get('/api/v1/revenue/settings/', () => HttpResponse.json(current)),
    http.patch('/api/v1/revenue/settings/', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.push(body)
      if (body.horizon_days === 400) {
        return HttpResponse.json(
          { detail: 'Asegúrese de que este valor es menor o igual a 365.', code: 'validation_error', fields: { horizon_days: ['Asegúrese de que este valor es menor o igual a 365.'] } },
          { status: 400 },
        )
      }
      current = { ...current, ...body } as RevenueSettings
      return HttpResponse.json(current)
    }),
    http.get('/api/v1/revenue/recommendations/summary/', () => HttpResponse.json({})),
  )
  return patches
}

/** The switch once the permissions of the user are known (read-only until then). */
async function enabledSwitch(name: string) {
  const control = await screen.findByRole('switch', { name })
  await waitFor(() => expect(control).toBeEnabled())
  return control
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('revenue settings', () => {
  it('shows the settings of the property', async () => {
    mockSettingsApi()
    renderWithProviders(<SettingsPanel />)

    expect(await screen.findByRole('switch', { name: 'Revenue management activo' })).toBeChecked()
    expect(screen.getByRole('switch', { name: 'Aplicar automáticamente' })).not.toBeChecked()
    expect(screen.getByLabelText('Horizonte (noches)')).toHaveValue('120')
    expect(screen.getByLabelText('Cambio máximo diario (%)')).toHaveValue('20')
    expect(screen.getByLabelText('Cambio mínimo (%)')).toHaveValue('2')
    expect(screen.getByLabelText('Redondeo de precios')).toHaveValue('1.000')
  })

  it('asks before applying recommendations automatically, and only then saves', async () => {
    const patches = mockSettingsApi()
    const { user } = renderWithProviders(<SettingsPanel />)

    await user.click(await enabledSwitch('Aplicar automáticamente'))
    const dialog = await screen.findByRole('dialog', { name: '¿Aplicar las recomendaciones automáticamente?' })
    expect(patches).toHaveLength(0)
    await user.click(within(dialog).getByRole('button', { name: 'Activar' }))

    await waitFor(() => expect(patches).toEqual([{ auto_apply: true }]))
    expect(await screen.findByText('Aplicar automáticamente activado')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Aplicar automáticamente' })).toBeChecked())
  })

  it('does nothing when the confirmation is cancelled', async () => {
    const patches = mockSettingsApi()
    const { user } = renderWithProviders(<SettingsPanel />)

    await user.click(await enabledSwitch('Aplicar automáticamente'))
    const dialog = await screen.findByRole('dialog', { name: '¿Aplicar las recomendaciones automáticamente?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(patches).toHaveLength(0)
    expect(screen.getByRole('switch', { name: 'Aplicar automáticamente' })).not.toBeChecked()
  })

  it('turns auto-apply off right away', async () => {
    const patches = mockSettingsApi({ ...SETTINGS, auto_apply: true })
    const { user } = renderWithProviders(<SettingsPanel />)

    await user.click(await enabledSwitch('Aplicar automáticamente'))
    await waitFor(() => expect(patches).toEqual([{ auto_apply: false }]))
  })

  it('saves the limits of every run and shows what the server refused', async () => {
    const patches = mockSettingsApi()
    const { user } = renderWithProviders(<SettingsPanel />)

    const horizon = await screen.findByLabelText('Horizonte (noches)')
    await waitFor(() => expect(horizon).toBeEnabled()) // editable once the permissions of the user are known
    await user.clear(horizon)
    await user.type(horizon, '90')
    const maxChange = screen.getByLabelText('Cambio máximo diario (%)')
    await user.clear(maxChange)
    await user.type(maxChange, '15')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ horizon_days: 90, max_daily_change_percent: '15', min_change_percent: '2', price_rounding: '1000' })
    expect(await screen.findByText('Ajustes guardados')).toBeInTheDocument()

    await user.clear(horizon)
    await user.type(horizon, '400')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(await screen.findByText('Asegúrese de que este valor es menor o igual a 365.')).toBeInTheDocument()
    expect(horizon).toHaveAttribute('aria-invalid', 'true')
  })

  it('is read-only without revenue.manage', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['revenue.view'], 'front_desk')] }))
    mockSettingsApi()
    const { queryClient } = renderWithProviders(<SettingsPanel />)

    await waitFor(() => expect(queryClient.getQueryData(['me'])).toBeTruthy()) // permissions known
    expect(await screen.findByRole('switch', { name: 'Aplicar automáticamente' })).toBeDisabled()
    expect(screen.getByLabelText('Horizonte (noches)')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument()
    expect(screen.getByText('Solo quien gestiona revenue puede cambiar estos ajustes.')).toBeInTheDocument()
  })
})
