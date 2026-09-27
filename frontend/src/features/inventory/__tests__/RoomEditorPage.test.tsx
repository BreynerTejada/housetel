import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { Room } from '../api'
import RoomEditorPage from '../pages/RoomEditorPage'
import { amenities, dormType, effectiveResponse, makeRoom, minibarField, orientationField, standardType } from './fixtures'

const BASE = '/api/v1/inventory'

function serve(room: Room, { patched }: { patched?: Record<string, unknown>[] } = {}) {
  const roomType = room.kind === 'dorm' ? dormType : standardType
  server.use(
    http.get(`${BASE}/rooms/${room.id}/`, () => HttpResponse.json(room)),
    http.get(`${BASE}/rooms/${room.id}/effective/`, () => HttpResponse.json(effectiveResponse(room, roomType))),
    http.get(`${BASE}/room-types/`, () => HttpResponse.json([standardType, dormType])),
    http.get(`${BASE}/amenities/`, () => HttpResponse.json(amenities)),
    http.get(`${BASE}/custom-fields/`, () => HttpResponse.json([orientationField, minibarField])),
    http.get(`${BASE}/rooms/${room.id}/beds/`, () => HttpResponse.json([])),
    http.get(`${BASE}/blocks/`, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    http.patch(`${BASE}/rooms/${room.id}/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patched?.push(body)
      return HttpResponse.json(room)
    }),
  )
}

function renderEditor(room: Room) {
  return renderWithProviders(<RoomEditorPage />, {
    route: `/app/settings/rooms/${room.id}`,
    path: '/app/settings/rooms/:roomId',
  })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('RoomEditorPage', () => {
  it('shows inherited values muted with their category and overridden ones as the room’s own', async () => {
    const room = makeRoom({ overrides: { max_adults: 3 } })
    serve(room)
    renderEditor(room)

    const size = await screen.findByRole('group', { name: 'Tamaño (m²)' })
    expect(within(size).getByText('22 m²')).toBeInTheDocument()
    expect(within(size).getByText('Heredado de Estándar')).toBeInTheDocument()
    expect(within(size).getByRole('button', { name: 'Sobrescribir Tamaño (m²)' })).toBeInTheDocument()

    const adults = screen.getByRole('group', { name: 'Adultos máximos' })
    expect(within(adults).getByRole('spinbutton')).toHaveValue(3)
    expect(within(adults).getByText('Propio')).toBeInTheDocument()
    expect(within(adults).getByText('La categoría dice 2')).toBeInTheDocument()
    expect(within(adults).getByRole('button', { name: 'Restaurar herencia de Adultos máximos' })).toBeInTheDocument()
  })

  it('overrides a field starting from the inherited value and restores another, then saves only the overrides left', async () => {
    const room = makeRoom({ overrides: { max_adults: 3 } })
    const patched: Record<string, unknown>[] = []
    serve(room, { patched })
    const { user } = renderEditor(room)

    const size = await screen.findByRole('group', { name: 'Tamaño (m²)' })
    await user.click(within(size).getByRole('button', { name: 'Sobrescribir Tamaño (m²)' }))
    const input = within(size).getByRole('spinbutton')
    expect(input).toHaveValue(22)
    await user.clear(input)
    await user.type(input, '26')

    const adults = screen.getByRole('group', { name: 'Adultos máximos' })
    await user.click(within(adults).getByRole('button', { name: 'Restaurar herencia de Adultos máximos' }))
    expect(within(adults).getByText('Heredado de Estándar')).toBeInTheDocument()
    expect(within(adults).queryByRole('spinbutton')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await screen.findByText('Habitación guardada')
    expect(patched).toHaveLength(1)
    expect(patched[0]?.overrides).toEqual({ size_m2: '26' })
  })

  it('warns before saving when the effective occupancy would not hold', async () => {
    const room = makeRoom()
    const patched: Record<string, unknown>[] = []
    serve(room, { patched })
    const { user } = renderEditor(room)

    const adults = await screen.findByRole('group', { name: 'Adultos máximos' })
    await user.click(within(adults).getByRole('button', { name: 'Sobrescribir Adultos máximos' }))
    const input = within(adults).getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '5')

    expect(within(adults).getByText('No puede superar la ocupación máxima (3)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
    expect(patched).toHaveLength(0)
  })

  it('shows a server error of a custom field next to it, on its tab', async () => {
    const room = makeRoom()
    serve(room)
    server.use(
      http.patch(`${BASE}/rooms/${room.id}/`, () =>
        HttpResponse.json(
          { detail: 'Este campo es obligatorio', code: 'validation_error', fields: { custom_values: { minibar: ['Este campo es obligatorio'] } } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderEditor(room)

    const floor = await screen.findByRole('textbox', { name: 'Piso' })
    await user.clear(floor)
    await user.type(floor, '2')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await screen.findByRole('tab', { name: 'Campos personalizados, con errores', selected: true })).toBeInTheDocument()
    const minibar = screen.getByRole('group', { name: 'Minibar surtido' })
    expect(within(minibar).getByText('Este campo es obligatorio')).toBeInTheDocument()
  })

  it('marks the room number when the server says it is taken', async () => {
    const room = makeRoom()
    serve(room)
    server.use(
      http.patch(`${BASE}/rooms/${room.id}/`, () =>
        HttpResponse.json(
          { detail: 'Ya existe una habitación con este número', code: 'validation_error', fields: { number: ['Ya existe una habitación con este número'] } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderEditor(room)

    const number = await screen.findByRole('textbox', { name: 'Número' })
    await user.clear(number)
    await user.type(number, '102')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    const panel = await screen.findByRole('tabpanel', { name: 'Atributos, con errores' })
    expect(await within(panel).findByText('Ya existe una habitación con este número')).toBeInTheDocument()
    expect(number).toHaveAttribute('aria-invalid', 'true')
  })

  it('stays on the tab it saved from when the saved room comes back from the server', async () => {
    let current = makeRoom()
    let reads = 0
    serve(current)
    server.use(
      http.get(`${BASE}/rooms/${current.id}/`, () => {
        reads += 1
        return HttpResponse.json(current)
      }),
      http.patch(`${BASE}/rooms/${current.id}/`, async ({ request }) => {
        current = { ...current, ...((await request.json()) as Partial<Room>), updated_at: '2026-09-26T09:00:00-05:00' }
        return HttpResponse.json(current)
      }),
    )
    const { user } = renderEditor(current)

    await user.click(await screen.findByRole('tab', { name: 'Amenidades' }))
    await user.click(screen.getByRole('button', { name: /Bañera/ }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await screen.findByText('Habitación guardada')
    await waitFor(() => expect(reads).toBeGreaterThan(1)) // the refetch after saving
    expect(screen.getByRole('tab', { name: /Amenidades/, selected: true })).toBeInTheDocument()
  })

  it('keeps what the user is typing when the room changes on the server meanwhile', async () => {
    let current = makeRoom()
    serve(current)
    server.use(http.get(`${BASE}/rooms/${current.id}/`, () => HttpResponse.json(current)))
    const { user, queryClient } = renderEditor(current)

    const floor = await screen.findByRole('textbox', { name: 'Piso' })
    await user.clear(floor)
    await user.type(floor, '7')
    // housekeeping marks the room dirty and someone leaves a note: a newer room arrives (refetch on focus…)
    current = { ...current, housekeeping_status: 'dirty', notes: 'Ventana rota', updated_at: '2026-09-26T09:30:00-05:00' }
    await act(() => queryClient.invalidateQueries({ queryKey: ['inventory'] }))

    expect((await screen.findAllByText('Sucia')).length).toBeGreaterThan(0)
    expect(screen.getByRole('textbox', { name: 'Piso' })).toHaveValue('7')
    expect(screen.getByRole('textbox', { name: 'Notas internas' })).toHaveValue('Ventana rota')
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled()
  })

  it('links to the category it inherits from', async () => {
    const room = makeRoom()
    serve(room)
    renderEditor(room)

    const link = await screen.findByRole('link', { name: 'Abrir la categoría Estándar' })
    expect(link).toHaveAttribute('href', `/app/settings/room-types/${standardType.id}`)
  })

  it('shows the beds tab only for dorm rooms', async () => {
    const privateRoom = makeRoom()
    serve(privateRoom)
    const { unmount } = renderEditor(privateRoom)
    expect(await screen.findByRole('tab', { name: 'Atributos' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Camas' })).not.toBeInTheDocument()
    unmount()

    const dormRoom = makeRoom({ id: 'room-d1', number: 'D1' }, dormType)
    serve(dormRoom)
    renderEditor(dormRoom)
    expect(await screen.findByRole('tab', { name: 'Camas' })).toBeInTheDocument()
  })
})
