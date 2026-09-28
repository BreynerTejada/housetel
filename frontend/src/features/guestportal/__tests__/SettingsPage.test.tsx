import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PortalSettings } from '../api'
import SettingsPage from '../pages/SettingsPage'

const URL = '/api/v1/guestportal/settings/'

const settings: PortalSettings = {
  checkin_opens_days_before: 7,
  require_document_photo: true,
  require_signature: true,
  auto_approve_extras: true,
  allow_guest_cancellation: true,
  allow_guest_modification: true,
  terms: { es: 'Acepto las reglas de Casa Aurora.', en: 'I accept the rules of Casa Aurora.' },
  updated_at: '2026-10-01T10:00:00-05:00',
}

function serve() {
  const patches: unknown[] = []
  let current = settings
  server.use(
    http.get(URL, () => HttpResponse.json(current)),
    http.patch(URL, async ({ request }) => {
      const body = (await request.json()) as Partial<PortalSettings>
      patches.push(body)
      current = { ...current, ...body }
      return HttpResponse.json(current)
    }),
  )
  return patches
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
})

describe('Guest portal settings', () => {
  it('shows what guests can do today', async () => {
    mockMe(makeMe())
    serve()
    renderWithProviders(<SettingsPage />)

    expect(await screen.findByRole('heading', { name: 'Portal del huésped', level: 1 })).toBeInTheDocument()
    expect(await screen.findByLabelText('Se abre días antes de la llegada')).toHaveValue(7)
    expect(screen.getByRole('switch', { name: 'Pedir foto del documento' })).toBeChecked()
    expect(screen.getByRole('switch', { name: 'Aprobar extras automáticamente' })).toBeChecked()
    expect(screen.getByLabelText('Español')).toHaveValue('Acepto las reglas de Casa Aurora.')
  })

  it('saves only what changed', async () => {
    mockMe(makeMe())
    const patches = serve()
    const { user } = renderWithProviders(<SettingsPage />)

    const days = await screen.findByLabelText('Se abre días antes de la llegada')
    await waitFor(() => expect(days).toBeEnabled()) // permissions come with `me`
    await user.clear(days)
    await user.type(days, '3')
    await user.click(screen.getByRole('switch', { name: 'Aprobar extras automáticamente' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await screen.findByText('Configuración guardada')).toBeInTheDocument()
    expect(patches).toEqual([{ checkin_opens_days_before: 3, auto_approve_extras: false }])
  })

  it('keeps the window between 0 and 60 days', async () => {
    mockMe(makeMe())
    const patches = serve()
    const { user } = renderWithProviders(<SettingsPage />)

    const days = await screen.findByLabelText('Se abre días antes de la llegada')
    await waitFor(() => expect(days).toBeEnabled()) // permissions come with `me`
    await user.clear(days)
    await user.type(days, '90')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(days).toHaveAccessibleDescription(/Máximo 60/)
    expect(days).toHaveAttribute('aria-invalid', 'true')
    expect(patches).toEqual([])
  })

  it('is read-only without permission to manage the portal', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['guestportal.view'], 'front_desk')] }))
    serve()
    renderWithProviders(<SettingsPage />)

    expect(await screen.findByText('Tu rol puede ver esta configuración pero no cambiarla.')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Pedir firma' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument()
  })
})
