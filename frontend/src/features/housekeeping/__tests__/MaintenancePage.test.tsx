import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '@/lib/api'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { MaintenanceTicket } from '../api'
import MaintenancePage from '../pages/MaintenancePage'
import { housekeeperMe, JORGE, LUZ, maintenanceMe, makePhoto, makeRoomRef, makeTicket, page, serveBoard } from './fixtures'

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

afterEach(() => {
  vi.restoreAllMocks()
})

const OPEN_TICKETS = [
  makeTicket(),
  makeTicket({
    id: 'ticket-2',
    title: 'Aire acondicionado no enfría',
    room: makeRoomRef('201', { housekeeping_status: 'out_of_service' }),
    priority: 'high',
    blocks_room: true,
    blocked_until: '2026-09-27',
    block: { id: 'block-1', start_date: '2026-09-25', end_date: '2026-09-27', released_at: null },
  }),
  makeTicket({
    id: 'ticket-3',
    title: 'Bombillo fundido en el pasillo',
    room: null,
    location: 'Pasillo del piso 2',
    priority: 'low',
    status: 'in_progress',
    assigned_to: JORGE,
    started_at: '2026-09-25T10:00:00-05:00',
  }),
]

/** Tickets by status (what the list asks for) and the rooms of the board for the report form. */
function serveTickets(tickets: MaintenanceTicket[] = OPEN_TICKETS) {
  const searches: string[] = []
  server.use(
    http.get('/api/v1/housekeeping/tickets/', ({ request }) => {
      const url = new URL(request.url)
      searches.push(url.search)
      const statuses = url.searchParams.getAll('status')
      const room = url.searchParams.get('room')
      return HttpResponse.json(
        page(
          tickets.filter(
            (ticket) => (statuses.length === 0 || statuses.includes(ticket.status)) && (!room || ticket.room?.id === room),
          ),
        ),
      )
    }),
  )
  serveBoard()
  return searches
}

describe('MaintenancePage', () => {
  it('lists the pending damage split into open and in progress, marking the blocked room', async () => {
    mockMe(maintenanceMe())
    const searches = serveTickets()
    renderWithProviders(<MaintenancePage />)

    const open = await screen.findByRole('region', { name: /^Abiertos/ })
    const blocking = within(open).getByRole('button', { name: /Aire acondicionado no enfría/ })
    expect(blocking).toHaveTextContent('201')
    expect(blocking).toHaveTextContent('Bloquea la habitación hasta el 27 sep')
    expect(blocking).toHaveTextContent('Alta')
    expect(within(open).getByRole('button', { name: /Grifo del lavamanos gotea/ })).toHaveTextContent('Luz Marina Pérez')
    const working = screen.getByRole('region', { name: /^En curso/ })
    const bulb = within(working).getByRole('button', { name: /Bombillo fundido/ })
    expect(bulb).toHaveTextContent('Pasillo del piso 2')
    expect(bulb).toHaveTextContent('Jorge Técnico')
    expect(searches[0]).toContain('status=open&status=in_progress')
  })

  it('shows the solved ones on their own tab', async () => {
    mockMe(maintenanceMe())
    const solved = makeTicket({ id: 'ticket-9', title: 'Puerta del clóset descolgada', status: 'resolved', resolution_notes: 'Bisagra nueva' })
    const searches = serveTickets([...OPEN_TICKETS, solved])
    const { user } = renderWithProviders(<MaintenancePage />)

    await screen.findByRole('region', { name: /^Abiertos/ })
    await user.click(screen.getByRole('radio', { name: 'Resueltos' }))

    expect(await screen.findByRole('button', { name: /Puerta del clóset descolgada/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Grifo del lavamanos/ })).not.toBeInTheDocument()
    expect(searches.at(-1)).toContain('status=resolved')
  })

  it('starts working on a ticket and resolves it with what was done', async () => {
    mockMe(maintenanceMe())
    serveTickets()
    const calls: { path: string; body: unknown }[] = []
    server.use(
      http.post('/api/v1/housekeeping/tickets/:id/start/', ({ params }) => {
        calls.push({ path: `start/${params.id}`, body: null })
        return HttpResponse.json(makeTicket({ status: 'in_progress', assigned_to: JORGE }))
      }),
      http.post('/api/v1/housekeeping/tickets/:id/resolve/', async ({ params, request }) => {
        calls.push({ path: `resolve/${params.id}`, body: await request.json() })
        return HttpResponse.json(makeTicket({ status: 'resolved' }))
      }),
    )
    const { user } = renderWithProviders(<MaintenancePage />)

    await user.click(await screen.findByRole('button', { name: /Grifo del lavamanos gotea/ }))
    const panel = await screen.findByRole('dialog', { name: 'Grifo del lavamanos gotea' })
    await user.click(within(panel).getByRole('button', { name: 'Empezar' }))
    await user.type(within(panel).getByLabelText('Qué se hizo'), 'Cambié el empaque')
    await user.click(within(panel).getByRole('button', { name: 'Marcar resuelto' }))

    await waitFor(() =>
      expect(calls).toEqual([
        { path: 'start/ticket-1', body: null },
        { path: 'resolve/ticket-1', body: { notes: 'Cambié el empaque' } },
      ]),
    )
  })

  it('shows the photos of a report without exposing them publicly', async () => {
    mockMe(maintenanceMe())
    serveTickets([makeTicket({ photos: [makePhoto()] })])
    const fileRequests: string[] = []
    server.use(
      http.get('/api/v1/housekeeping/ticket-photos/:id/file/', ({ request }) => {
        fileRequests.push(new URL(request.url).pathname)
        return new HttpResponse(new Blob(['jpeg'], { type: 'image/jpeg' }), { headers: { 'Content-Type': 'image/jpeg' } })
      }),
    )
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:photo')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const { user } = renderWithProviders(<MaintenancePage />)

    await user.click(await screen.findByRole('button', { name: /Grifo del lavamanos gotea/ }))
    const panel = await screen.findByRole('dialog', { name: 'Grifo del lavamanos gotea' })

    expect(await within(panel).findByRole('img', { name: 'Foto 1 del reporte' })).toHaveAttribute('src', 'blob:photo')
    expect(fileRequests).toEqual(['/api/v1/housekeeping/ticket-photos/photo-1/file/'])
  })

  it('warns before blocking a room with bookings and lets maintenance block it anyway', async () => {
    mockMe(maintenanceMe())
    serveTickets()
    server.use(http.get('/api/v1/housekeeping/staff/', () => HttpResponse.json({ housekeepers: [], maintenance: [{ ...JORGE, open_tickets: 1 }] })))
    const forms: FormData[] = []
    vi.spyOn(api, 'post').mockImplementation(async (_path, _body, opts) => {
      forms.push(opts?.formData as FormData)
      if (forms.length === 1)
        throw new ApiError(409, 'room_has_reservations', 'La habitación 102 tiene reservas en esas fechas: HT-7K2M9Q', undefined, {
          reservations: ['HT-7K2M9Q'],
        })
      return makeTicket() as never
    })
    const { user } = renderWithProviders(<MaintenancePage />)

    await user.click(await screen.findByRole('button', { name: 'Reportar daño' }))
    const sheet = await screen.findByRole('dialog', { name: 'Reportar un daño' })
    await user.click(within(sheet).getByRole('combobox', { name: 'Habitación' }))
    await user.click(await screen.findByRole('option', { name: '102' }))
    await user.type(within(sheet).getByLabelText('¿Qué pasó?'), 'Humedad en el techo')
    await user.click(within(sheet).getByRole('switch', { name: 'La habitación no se puede usar' }))
    await user.click(within(sheet).getByRole('button', { name: 'Enviar reporte' }))

    expect(await within(sheet).findByText('La habitación 102 tiene reservas en esas fechas: HT-7K2M9Q')).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Bloquear de todas formas' }))

    await waitFor(() => expect(forms).toHaveLength(2))
    expect(forms[0].get('room_id')).toBe('room-102')
    expect(forms[0].get('force')).toBeNull()
    expect(forms[1].get('force')).toBe('true')
  })

  it('reports damage in a common area', async () => {
    mockMe(housekeeperMe())
    serveTickets()
    const forms: FormData[] = []
    vi.spyOn(api, 'post').mockImplementation(async (_path, _body, opts) => {
      forms.push(opts?.formData as FormData)
      return makeTicket() as never
    })
    const { user } = renderWithProviders(<MaintenancePage />)

    await user.click(await screen.findByRole('button', { name: 'Reportar daño' }))
    const sheet = await screen.findByRole('dialog', { name: 'Reportar un daño' })
    await user.type(within(sheet).getByLabelText('Lugar'), 'Recepción')
    await user.type(within(sheet).getByLabelText('¿Qué pasó?'), 'Silla rota')
    await user.click(within(sheet).getByRole('button', { name: 'Enviar reporte' }))

    await waitFor(() => expect(forms).toHaveLength(1))
    expect(forms[0].get('room_id')).toBeNull()
    expect(forms[0].get('location')).toBe('Recepción')
    expect(forms[0].get('title')).toBe('Silla rota')
  })

  it('lets housekeepers follow their reports but not work them', async () => {
    mockMe(housekeeperMe())
    serveTickets()
    const { user } = renderWithProviders(<MaintenancePage />)

    await user.click(await screen.findByRole('button', { name: /Grifo del lavamanos gotea/ }))
    const panel = await screen.findByRole('dialog', { name: 'Grifo del lavamanos gotea' })
    expect(within(panel).getByText(`Reportado por ${LUZ.full_name}`, { exact: false })).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Empezar' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Marcar resuelto' })).not.toBeInTheDocument()
  })

  it('opens on the tickets of one room when coming from the board', async () => {
    mockMe(maintenanceMe())
    const searches = serveTickets()
    const { user } = renderWithProviders(<MaintenancePage />, { route: '/app/maintenance?room=room-201' })

    expect(await screen.findByRole('button', { name: /Aire acondicionado no enfría/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Grifo del lavamanos/ })).not.toBeInTheDocument()
    expect(searches[0]).toContain('room=room-201')
    await user.click(screen.getByRole('button', { name: 'Ver todas las habitaciones' }))
    expect(await screen.findByRole('button', { name: /Grifo del lavamanos gotea/ })).toBeInTheDocument()
  })
})
