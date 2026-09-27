import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import RoomsPage from '../pages/RoomsPage'
import { dormType, makeRoom, minibarField, orientationField, standardType } from './fixtures'

const BASE = '/api/v1/inventory'

const rooms = [
  makeRoom({ id: 'r101', number: '101', floor: '1' }),
  makeRoom({ id: 'r102', number: '102', floor: '1', housekeeping_status: 'dirty', overrides: { view: 'sea' } }),
  makeRoom({ id: 'r201', number: '201', floor: '2' }),
  makeRoom({ id: 'rd1', number: 'D1', floor: '' }, dormType),
]

function serve(bulkBodies: unknown[] = []) {
  server.use(
    http.get(`${BASE}/rooms/`, () => HttpResponse.json(rooms)),
    http.get(`${BASE}/room-types/`, () => HttpResponse.json([standardType, dormType])),
    http.get(`${BASE}/custom-fields/`, () => HttpResponse.json([orientationField, minibarField])),
    http.post(`${BASE}/rooms/bulk-update/`, async ({ request }) => {
      const body = (await request.json()) as { ids: string[] }
      bulkBodies.push(body)
      return HttpResponse.json({ updated: body.ids.length, rooms: rooms.filter((room) => body.ids.includes(room.id)) })
    }),
  )
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('RoomsPage', () => {
  it('groups rooms under their category with the rack tag, status and own values', async () => {
    serve()
    renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    const standard = await screen.findByRole('rowgroup', { name: /Estándar/ })
    expect(within(standard).getAllByRole('row').map((row) => within(row).queryByText(/^\d{3}$/)?.textContent).filter(Boolean)).toEqual([
      '101',
      '102',
      '201',
    ])
    const row102 = within(standard).getByRole('row', { name: /102/ })
    expect(within(row102).getByText('Sucia')).toBeInTheDocument()
    expect(within(row102).getByText('1 propio')).toBeInTheDocument()
    expect(screen.getByRole('rowgroup', { name: /Dormitorio mixto 6 camas/ })).toBeInTheDocument()
  })

  it('edits the selected rooms in bulk', async () => {
    const bodies: unknown[] = []
    serve(bodies)
    const { user } = renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await user.click(await screen.findByRole('checkbox', { name: 'Seleccionar habitación 101' }))
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar habitación 201' }))
    const bar = screen.getByRole('region', { name: 'Selección' })
    expect(within(bar).getByText('2 seleccionadas')).toBeInTheDocument()

    await user.click(within(bar).getByRole('button', { name: 'Editar en bloque' }))
    await user.click(await screen.findByRole('combobox', { name: 'Campo a cambiar' }))
    await user.click(await screen.findByRole('option', { name: 'Piso' }))
    await user.type(screen.getByRole('textbox', { name: 'Nuevo valor' }), '5')
    await user.click(screen.getByRole('button', { name: 'Aplicar a 2 habitaciones' }))

    expect(await screen.findByText('2 habitaciones actualizadas')).toBeInTheDocument()
    expect(bodies).toEqual([{ ids: ['r101', 'r201'], set: { floor: '5' }, reset: [] }])
  })

  it('restores inheritance in bulk for overridable fields', async () => {
    const bodies: unknown[] = []
    serve(bodies)
    const { user } = renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await user.click(await screen.findByRole('checkbox', { name: 'Seleccionar habitación 102' }))
    await user.click(within(screen.getByRole('region', { name: 'Selección' })).getByRole('button', { name: 'Editar en bloque' }))
    await user.click(await screen.findByRole('combobox', { name: 'Campo a cambiar' }))
    await user.click(await screen.findByRole('option', { name: 'Vista' }))
    await user.click(screen.getByRole('radio', { name: 'Volver a heredar de la categoría' }))
    await user.click(screen.getByRole('button', { name: 'Aplicar a 1 habitación' }))

    await screen.findByText('1 habitación actualizada')
    expect(bodies).toEqual([{ ids: ['r102'], set: {}, reset: ['view'] }])
  })

  it('says which rooms a rejected bulk edit would break', async () => {
    serve()
    server.use(
      http.post(`${BASE}/rooms/bulk-update/`, () =>
        HttpResponse.json(
          { detail: 'La ocupación resultante no es válida', code: 'validation_error', fields: { max_adults: ['Ocupación inválida en 101, 201'] } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await user.click(await screen.findByRole('checkbox', { name: 'Seleccionar habitación 101' }))
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar habitación 201' }))
    await user.click(within(screen.getByRole('region', { name: 'Selección' })).getByRole('button', { name: 'Editar en bloque' }))
    await user.click(await screen.findByRole('combobox', { name: 'Campo a cambiar' }))
    await user.click(await screen.findByRole('option', { name: 'Adultos máximos' }))
    await user.type(screen.getByRole('spinbutton', { name: 'Nuevo valor' }), '9')
    await user.click(screen.getByRole('button', { name: 'Aplicar a 2 habitaciones' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('La ocupación resultante no es válida')
    expect(alert).toHaveTextContent('Ocupación inválida en 101, 201')
  })

  it('opens filtered by the category in the address (from a category editor)', async () => {
    serve()
    renderWithProviders(<RoomsPage />, { route: `/app/settings/rooms?room_type=${dormType.id}` })

    expect(await screen.findByRole('rowgroup', { name: /Dormitorio mixto 6 camas/ })).toBeInTheDocument()
    expect(screen.queryByRole('rowgroup', { name: /Estándar/ })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Categoría' })).toHaveTextContent('D6 · Dormitorio mixto 6 camas')
  })

  it('bulk-creates in the category being filtered', async () => {
    serve()
    const { user } = renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await user.click(await screen.findByRole('combobox', { name: 'Categoría' }))
    await user.click(await screen.findByRole('option', { name: 'D6 · Dormitorio mixto 6 camas' }))
    await user.click(screen.getByRole('button', { name: 'Crear en bloque' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('combobox', { name: 'Categoría' })).toHaveTextContent('D6 · Dormitorio mixto 6 camas')
  })

  it('retries every list that failed to load', async () => {
    serve()
    let typeReads = 0
    server.use(
      http.get(`${BASE}/room-types/`, () => {
        typeReads += 1
        return typeReads === 1 ? HttpResponse.json({ detail: 'Error', code: 'server_error' }, { status: 500 }) : HttpResponse.json([standardType, dormType])
      }),
    )
    const { user } = renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))

    expect(await screen.findByRole('rowgroup', { name: /Estándar/ })).toBeInTheDocument()
  })

  it('is read-only for staff without inventory.manage', async () => {
    serve()
    mockMe(makeMe({ memberships: [auroraMembership(['inventory.view'], 'front_desk')] }))
    renderWithProviders(<RoomsPage />, { route: '/app/settings/rooms' })

    await screen.findByRole('rowgroup', { name: /Estándar/ })
    expect(screen.queryByRole('checkbox', { name: 'Seleccionar habitación 101' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Crear en bloque' })).not.toBeInTheDocument()
  })
})
