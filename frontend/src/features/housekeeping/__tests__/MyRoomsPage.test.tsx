import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { HkTask } from '../api'
import MyRoomsPage from '../pages/MyRoomsPage'
import { housekeeperMe, LUZ, makeTask, makeTicket, page } from './fixtures'

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

/** A small live backend for "my tasks": start/finish change the task and the next GET reflects it. */
function serveMyTasks(initial: HkTask[]) {
  let tasks = [...initial]
  const requests: { method: string; path: string; body: unknown; search: string }[] = []
  const update = (id: string, changes: Partial<HkTask>) => {
    tasks = tasks.map((task) => (task.id === id ? { ...task, ...changes } : task))
    return tasks.find((task) => task.id === id)
  }
  server.use(
    http.get('/api/v1/housekeeping/tasks/', ({ request }) => {
      const url = new URL(request.url)
      requests.push({ method: 'GET', path: url.pathname, body: null, search: url.search })
      return HttpResponse.json(page(tasks))
    }),
    http.post('/api/v1/housekeeping/tasks/:id/start/', ({ params }) => {
      requests.push({ method: 'POST', path: `start/${params.id}`, body: null, search: '' })
      return HttpResponse.json(update(String(params.id), { status: 'in_progress', started_at: '2026-09-25T10:00:00-05:00' }))
    }),
    http.post('/api/v1/housekeeping/tasks/:id/finish/', async ({ params, request }) => {
      const body = await request.json()
      requests.push({ method: 'POST', path: `finish/${params.id}`, body, search: '' })
      return HttpResponse.json(
        update(String(params.id), { status: 'done', finished_at: '2026-09-25T10:25:00-05:00', finished_by: LUZ }),
      )
    }),
  )
  return requests
}

const DAY = [
  makeTask({ number: '101', status: 'done', kind: 'stayover', finished_at: '2026-09-25T09:40:00-05:00', finished_by: LUZ }),
  makeTask({ number: '102', status: 'in_progress', kind: 'stayover', estimated_minutes: 15, started_at: '2026-09-25T09:50:00-05:00' }),
  makeTask({
    number: '202',
    priority: 'high',
    estimated_minutes: 40,
    arrival_today: { code: 'HT-ARR202', eta: '15:00', is_vip: true },
    notes: 'Cambiar cortinas del baño',
  }),
  makeTask({ number: '201', waiting_for_checkout: true, estimated_minutes: 30 }),
]

describe('MyRoomsPage', () => {
  it('shows the room in progress first, then the next ones and what is already done', async () => {
    mockMe(housekeeperMe())
    const requests = serveMyTasks(DAY)
    renderWithProviders(<MyRoomsPage />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Mis habitaciones' })).toBeInTheDocument()
    const current = await screen.findByRole('region', { name: 'En curso' })
    expect(within(current).getByRole('article', { name: 'Habitación 102' })).toBeInTheDocument()
    const next = screen.getByRole('region', { name: /Siguientes/ })
    expect(within(next).getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual([
      'Habitación 202',
      'Habitación 201',
    ])
    const done = screen.getByRole('region', { name: /Terminadas/ })
    expect(within(done).getByText('101')).toBeInTheDocument()
    expect(screen.getByText('1 de 4 listas')).toBeInTheDocument()
    expect(screen.getByText('1 h 25 min por hacer')).toBeInTheDocument()
    expect(requests[0].search).toContain('mine=1')
  })

  it('tells what each room needs: arrival today, VIP, priority and the supervisor note', async () => {
    mockMe(housekeeperMe())
    serveMyTasks(DAY)
    renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 202' })
    expect(within(card).getByText('Limpieza de salida')).toBeInTheDocument()
    expect(within(card).getByText('Llega hoy · 15:00')).toBeInTheDocument()
    expect(within(card).getByText('VIP')).toBeInTheDocument()
    expect(within(card).getByText('Alta')).toBeInTheDocument()
    expect(within(card).getByText('Cambiar cortinas del baño')).toBeInTheDocument()
    expect(within(card).getByText('40 min')).toBeInTheDocument()
  })

  it('starts the next room with one tap and finishes it with a note', async () => {
    mockMe(housekeeperMe())
    const requests = serveMyTasks([makeTask({ number: '202' })])
    const { user } = renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 202' })
    await user.click(within(card).getByRole('button', { name: 'Iniciar' }))

    const current = await screen.findByRole('region', { name: 'En curso' })
    const started = within(current).getByRole('article', { name: 'Habitación 202' })
    await user.type(within(started).getByLabelText('Nota para la supervisión'), 'Faltan toallas')
    await user.click(within(started).getByRole('button', { name: 'Terminar' }))

    await waitFor(() =>
      expect(requests.filter((r) => r.method === 'POST')).toEqual([
        { method: 'POST', path: 'start/task-202', body: null, search: '' },
        { method: 'POST', path: 'finish/task-202', body: { notes: 'Faltan toallas' }, search: '' },
      ]),
    )
    const done = await screen.findByRole('region', { name: /Terminadas/ })
    expect(within(done).getByText('202')).toBeInTheDocument()
    expect(screen.getByText('1 de 1 lista')).toBeInTheDocument()
  })

  it('puts the rooms that can be cleaned now before the ones still waiting for a check-out', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([
      makeTask({ number: '105', priority: 'urgent', waiting_for_checkout: true }),
      makeTask({ number: '106', kind: 'stayover' }),
    ])
    renderWithProviders(<MyRoomsPage />)

    const next = await screen.findByRole('region', { name: /Siguientes/ })
    expect(within(next).getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual([
      'Habitación 106',
      'Habitación 105',
    ])
  })

  it('a departure waits until the guest checks out', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([makeTask({ number: '201', waiting_for_checkout: true })])
    renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 201' })
    expect(within(card).getByRole('button', { name: 'Iniciar' })).toBeDisabled()
    expect(within(card).getByText('El huésped aún no ha hecho check-out')).toBeInTheDocument()
  })

  it('explains why a room could not be started', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([makeTask({ number: '202' })])
    server.use(
      http.post('/api/v1/housekeeping/tasks/:id/start/', () =>
        HttpResponse.json(
          { detail: 'El huésped de la habitación 202 aún no ha hecho check-out', code: 'guest_in_room' },
          { status: 409 },
        ),
      ),
    )
    const { user } = renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 202' })
    await user.click(within(card).getByRole('button', { name: 'Iniciar' }))

    expect(await screen.findByText('El huésped de la habitación 202 aún no ha hecho check-out')).toBeInTheDocument()
  })

  it('reports damage with photos taken with the phone camera', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([makeTask({ number: '202', status: 'in_progress' })])
    // jsdom's File cannot go through Node's fetch, so the report is checked where it leaves the page: the
    // multipart body handed to the API client (multipart transport is covered by lib/api tests).
    let sent: { path: string; form?: FormData } | undefined
    const post = vi.spyOn(api, 'post').mockImplementation(async (path, _body, opts) => {
      sent = { path, form: opts?.formData }
      return makeTicket() as never
    })
    const { user } = renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 202' })
    await user.click(within(card).getByRole('button', { name: 'Reportar daño' }))
    const dialog = await screen.findByRole('dialog', { name: 'Reportar un daño' })
    expect(within(dialog).getByText('Habitación 202')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('¿Qué pasó?'), 'Espejo del baño roto')
    const camera = within(dialog).getByLabelText('Tomar o elegir fotos')
    expect(camera).toHaveAttribute('capture', 'environment')
    expect(camera).toHaveAttribute('accept', 'image/*')
    await user.upload(camera, new File(['jpeg-bytes'], 'foto.jpg', { type: 'image/jpeg' }))
    await user.click(within(dialog).getByRole('switch', { name: 'La habitación no se puede usar' }))
    await user.click(within(dialog).getByRole('button', { name: 'Enviar reporte' }))

    await waitFor(() => expect(sent?.path).toBe('/housekeeping/tickets/'))
    expect(sent?.form?.get('room_id')).toBe('room-202')
    expect(sent?.form?.get('title')).toBe('Espejo del baño roto')
    expect(sent?.form?.get('blocks_room')).toBe('true')
    expect(sent?.form?.get('blocked_until')).toBe('2026-09-26')
    expect((sent?.form?.getAll('photos')[0] as File).name).toBe('foto.jpg')
    expect(await screen.findByText('Reporte enviado a mantenimiento')).toBeInTheDocument()
    post.mockRestore()
  })

  it('does not send a report without saying what happened', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([makeTask({ number: '202' })])
    const post = vi.spyOn(api, 'post')
    const { user } = renderWithProviders(<MyRoomsPage />)

    const card = await screen.findByRole('article', { name: 'Habitación 202' })
    await user.click(within(card).getByRole('button', { name: 'Reportar daño' }))
    const dialog = await screen.findByRole('dialog', { name: 'Reportar un daño' })
    await user.click(within(dialog).getByRole('button', { name: 'Enviar reporte' }))

    expect(within(dialog).getByText('Escribe qué pasó')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('¿Qué pasó?')).toHaveAttribute('aria-invalid', 'true')
    expect(post).not.toHaveBeenCalled()
    post.mockRestore()
  })

  it('invites to wait for assignments when there is nothing to clean', async () => {
    mockMe(housekeeperMe())
    serveMyTasks([])
    renderWithProviders(<MyRoomsPage />)

    expect(await screen.findByText('No tienes habitaciones asignadas hoy')).toBeInTheDocument()
  })
})
