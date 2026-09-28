import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { widgets } from '../widgets'
import { makeSummary, supervisorMe } from './fixtures'

// The widget is lazy (the extension registry loads widgets.tsx eagerly): warm its module once.
beforeAll(() => import('../components/CleaningProgressWidget'), 60_000)

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
})

describe('Today panel widget', () => {
  it('registers the cleaning progress for whoever can see housekeeping', () => {
    expect(widgets.map(({ id, size, permission }) => ({ id, size, permission }))).toEqual([
      { id: 'housekeeping.progress', size: 'md', permission: 'housekeeping.view' },
    ])
  })

  it('shows how much of the day is clean and what needs attention', async () => {
    mockMe(supervisorMe())
    server.use(
      http.get('/api/v1/housekeeping/summary/', () =>
        HttpResponse.json(
          makeSummary({
            tasks: { total: 19, pending: 10, in_progress: 2, done: 7, inspections_pending: 0, unassigned: 3 },
            rooms: { total: 24, clean: 12, dirty: 9, inspected: 2, out_of_service: 1, occupied: 18 },
            tickets: { open: 2, blocking: 1 },
          }),
        ),
      ),
    )
    const [{ Component }] = widgets
    renderWithProviders(<Component />)

    const card = await screen.findByRole('region', { name: 'Limpieza de hoy' })
    expect(await within(card).findByText('7 de 19 tareas terminadas')).toBeInTheDocument()
    expect(within(card).getByRole('progressbar', { name: 'Tareas terminadas' })).toHaveAttribute('aria-valuenow', '7')
    expect(within(card).getByRole('group', { name: 'Sucias' })).toHaveTextContent('9')
    expect(within(card).getByText('3 sin asignar')).toBeInTheDocument()
    expect(within(card).getByText('2 daños abiertos · 1 bloquea habitación')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Ver tablero de limpieza' })).toHaveAttribute('href', '/app/housekeeping')
  })
})
