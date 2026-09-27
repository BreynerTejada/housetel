import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RoomTypesPage from '../pages/RoomTypesPage'
import { dormType, standardType } from './fixtures'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('RoomTypesPage', () => {
  it('lists each category with its units, capacity and beds', async () => {
    server.use(http.get('/api/v1/inventory/room-types/', () => HttpResponse.json([standardType, dormType])))
    renderWithProviders(<RoomTypesPage />, { route: '/app/settings/room-types' })

    const standard = await screen.findByRole('link', { name: /Estándar/ })
    expect(standard).toHaveAttribute('href', `/app/settings/room-types/${standardType.id}`)
    expect(within(standard).getByText('2 habitaciones')).toBeInTheDocument()
    expect(within(standard).getByText('2–3 personas')).toBeInTheDocument()
    expect(within(standard).getByText('1 × Queen · 22 m²')).toBeInTheDocument()

    const dorm = screen.getByRole('link', { name: /Dormitorio mixto 6 camas/ })
    expect(within(dorm).getByText('6 camas')).toBeInTheDocument()
    expect(within(dorm).getByText('Se vende por cama')).toBeInTheDocument()
  })

  it('invites to create the first category when there is none', async () => {
    server.use(http.get('/api/v1/inventory/room-types/', () => HttpResponse.json([])))
    renderWithProviders(<RoomTypesPage />, { route: '/app/settings/room-types' })
    expect(await screen.findByText('Crea tu primera categoría')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Nueva categoría' })[0]).toHaveAttribute('href', '/app/settings/room-types/new')
  })
})
