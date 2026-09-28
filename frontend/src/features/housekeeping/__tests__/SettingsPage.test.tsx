import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import SettingsPage from '../pages/SettingsPage'
import { SETTINGS, supervisorMe } from './fixtures'

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

function serveSettings() {
  const patches: unknown[] = []
  server.use(
    http.get('/api/v1/housekeeping/settings/', () => HttpResponse.json(SETTINGS)),
    http.patch('/api/v1/housekeeping/settings/', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.push(body)
      return HttpResponse.json({ ...SETTINGS, ...body })
    }),
  )
  return patches
}

describe('SettingsPage', () => {
  it('saves only what changed', async () => {
    mockMe(supervisorMe())
    const patches = serveSettings()
    const { user } = renderWithProviders(<SettingsPage />)

    const frequency = await screen.findByRole('combobox', { name: 'Repaso de huéspedes en casa' })
    expect(frequency).toHaveTextContent('Todos los días')
    await user.click(frequency)
    await user.click(await screen.findByRole('option', { name: 'Cada 2 días' }))
    await user.click(screen.getByRole('switch', { name: 'Exigir inspección' }))
    const shift = screen.getByLabelText('Minutos por turno')
    await user.clear(shift)
    await user.type(shift, '480')
    expect(screen.getByText(/8 h/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() =>
      expect(patches).toEqual([{ stayover_frequency_days: 2, require_inspection: true, minutes_per_shift: 480 }]),
    )
    expect(await screen.findByText('Configuración de limpieza guardada')).toBeInTheDocument()
  })

  it('does not save a shift out of range', async () => {
    mockMe(supervisorMe())
    const patches = serveSettings()
    const { user } = renderWithProviders(<SettingsPage />)

    await screen.findByRole('button', { name: 'Guardar cambios' }) // the session is loaded: fields are editable
    const shift = screen.getByLabelText('Minutos por turno')
    await user.clear(shift)
    await user.type(shift, '30')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await screen.findByText('Escribe entre 60 y 900 minutos')).toBeInTheDocument()
    expect(patches).toEqual([])
  })

  it('is read-only for people who do not supervise housekeeping', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['housekeeping.view', 'housekeeping.work'], 'housekeeping')] }))
    serveSettings()
    renderWithProviders(<SettingsPage />)

    expect(await screen.findByRole('switch', { name: 'Exigir inspección' })).toBeDisabled()
    expect(screen.getByText('Solo la supervisión de limpieza puede cambiar esta configuración.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument()
  })
})
