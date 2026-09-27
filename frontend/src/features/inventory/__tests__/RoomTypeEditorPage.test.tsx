import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { Photo, RoomType } from '../api'
import RoomTypeEditorPage from '../pages/RoomTypeEditorPage'
import { amenities, orientationField, standardType } from './fixtures'

const BASE = '/api/v1/inventory'

const photos: Photo[] = [
  { id: 'p1', url: '/media/photos/1.jpg', caption: { es: 'Vista general' }, sort_order: 1, room_type: standardType.id, created_at: '' },
  { id: 'p2', url: '/media/photos/2.jpg', caption: { es: 'La cama' }, sort_order: 2, room_type: standardType.id, created_at: '' },
  { id: 'p3', url: '/media/photos/3.jpg', caption: { es: 'El baño' }, sort_order: 3, room_type: standardType.id, created_at: '' },
]

function serve(captured: { method: string; path: string; body: unknown }[] = []) {
  const record = async (request: Request) => {
    captured.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() })
  }
  server.use(
    http.get(`${BASE}/room-types/${standardType.id}/`, () => HttpResponse.json(standardType)),
    http.get(`${BASE}/amenities/`, () => HttpResponse.json(amenities)),
    http.get(`${BASE}/custom-fields/`, () => HttpResponse.json([orientationField])),
    http.get(`${BASE}/room-types/${standardType.id}/photos/`, () => HttpResponse.json(photos)),
    http.post(`${BASE}/room-types/`, async ({ request }) => {
      await record(request)
      return HttpResponse.json({ ...standardType, id: 'rt-new', code: 'DM6' }, { status: 201 })
    }),
    http.patch(`${BASE}/room-types/${standardType.id}/`, async ({ request }) => {
      await record(request)
      return HttpResponse.json(standardType)
    }),
    http.post(`${BASE}/room-types/${standardType.id}/photos/reorder/`, async ({ request }) => {
      await record(request)
      return HttpResponse.json(photos)
    }),
    http.get(`${BASE}/room-types/rt-new/`, () => HttpResponse.json({ ...standardType, id: 'rt-new', code: 'DM6' })),
    http.get(`${BASE}/room-types/rt-new/photos/`, () => HttpResponse.json([])),
  )
}

function renderAt(id: string) {
  return renderWithProviders(<RoomTypeEditorPage />, {
    route: `/app/settings/room-types/${id}`,
    path: '/app/settings/room-types/:roomTypeId',
  })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
})

describe('RoomTypeEditorPage', () => {
  it('creates a dorm category: occupancy is per bed and the code comes from the name', async () => {
    const captured: { method: string; path: string; body: unknown }[] = []
    serve(captured)
    const { user, router } = renderAt('new')

    await user.type(await screen.findByRole('textbox', { name: 'Nombre (español)' }), 'Dormitorio mixto 6 camas')
    await user.click(screen.getByRole('radio', { name: /Dormitorio/ }))
    await user.click(screen.getByRole('tab', { name: 'Capacidad y camas' }))
    expect(screen.getByText('En un dormitorio cada cama es una unidad para una persona.')).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton', { name: 'Adultos máximos' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Crear categoría' }))

    await screen.findByText('Categoría creada')
    expect(captured[0]).toMatchObject({ method: 'POST', path: `${BASE}/room-types/` })
    const body = captured[0]?.body as Record<string, unknown>
    expect(body).toMatchObject({ code: '', name: { es: 'Dormitorio mixto 6 camas' }, kind: 'dorm' })
    expect(router.state.location.pathname).toBe('/app/settings/room-types/rt-new')
  })

  it('validates the occupancy of a private category before saving', async () => {
    serve()
    const { user } = renderAt('new')
    await user.type(await screen.findByRole('textbox', { name: 'Nombre (español)' }), 'Familiar')
    await user.click(screen.getByRole('tab', { name: 'Capacidad y camas' }))
    const adults = screen.getByRole('spinbutton', { name: 'Adultos máximos' })
    await user.clear(adults)
    await user.type(adults, '6')
    expect(screen.getByText('No puede superar la ocupación máxima (2)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear categoría' })).toBeDisabled()
  })

  it('saves amenity changes of an existing category', async () => {
    const captured: { method: string; path: string; body: unknown }[] = []
    serve(captured)
    const { user } = renderAt(standardType.id)

    await user.click(await screen.findByRole('tab', { name: 'Amenidades' }))
    await user.click(screen.getByRole('button', { name: 'Bañera' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await screen.findByText('Categoría guardada')
    expect(captured.at(-1)).toMatchObject({ method: 'PATCH' })
    expect((captured.at(-1)?.body as { amenities: string[] }).amenities).toEqual(['wifi', 'bathtub'])
  })

  it('shows a server error of a custom field on its tab', async () => {
    serve()
    server.use(
      http.patch(`${BASE}/room-types/${standardType.id}/`, () =>
        HttpResponse.json(
          { detail: 'Opción inválida: moon', code: 'validation_error', fields: { custom_values: { orientation: ['Opción inválida: moon'] } } },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderAt(standardType.id)

    const view = await screen.findByRole('combobox', { name: 'Vista' })
    expect(view).toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: /Accesible/ }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(await screen.findByRole('tab', { name: 'Campos personalizados, con errores', selected: true })).toBeInTheDocument()
    expect(screen.getByRole('tabpanel', { name: 'Campos personalizados, con errores' })).toHaveTextContent('Opción inválida: moon')
  })

  it('stays on the tab it saved from when the saved category comes back from the server', async () => {
    let current = standardType
    let reads = 0
    serve()
    server.use(
      http.get(`${BASE}/room-types/${standardType.id}/`, () => {
        reads += 1
        return HttpResponse.json(current)
      }),
      http.patch(`${BASE}/room-types/${standardType.id}/`, async ({ request }) => {
        current = { ...current, ...((await request.json()) as Partial<RoomType>), updated_at: '2026-09-26T09:00:00-05:00' }
        return HttpResponse.json(current)
      }),
    )
    const { user } = renderAt(standardType.id)

    await user.click(await screen.findByRole('tab', { name: 'Amenidades' }))
    await user.click(screen.getByRole('button', { name: 'Bañera' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await screen.findByText('Categoría guardada')
    await waitFor(() => expect(reads).toBeGreaterThan(1)) // the refetch after saving
    expect(screen.getByRole('tab', { name: 'Amenidades', selected: true })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument()
  })

  it('links to the rooms that inherit from it', async () => {
    serve()
    renderAt(standardType.id)

    const link = await screen.findByRole('link', { name: 'Ver sus 2 habitaciones' })
    expect(link).toHaveAttribute('href', `/app/settings/rooms?room_type=${standardType.id}`)
  })

  it('reorders photos with the keyboard-friendly move buttons', async () => {
    const captured: { method: string; path: string; body: unknown }[] = []
    serve(captured)
    const { user } = renderAt(standardType.id)

    await user.click(await screen.findByRole('tab', { name: 'Fotos' }))
    const gallery = await screen.findByRole('list', { name: 'Fotos de la categoría' })
    expect(within(gallery).getAllByRole('img').map((img) => img.getAttribute('src'))).toEqual([
      '/media/photos/1.jpg',
      '/media/photos/2.jpg',
      '/media/photos/3.jpg',
    ])
    await user.click(within(gallery).getByRole('button', { name: 'Mover la foto 3 antes' }))

    await screen.findByText('Orden de fotos guardado')
    expect(captured.at(-1)).toMatchObject({ path: `${BASE}/room-types/${standardType.id}/photos/reorder/`, body: { ids: ['p1', 'p3', 'p2'] } })
  })
})
