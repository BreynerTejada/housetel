import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import BoardPage from '../pages/BoardPage'
import { housekeeperMe, makeBoard, makeTask, serveBoard, supervisorMe } from './fixtures'

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

function tile(floor: HTMLElement, number: string) {
  return within(floor).getByRole('button', { name: new RegExp(`Habitación ${number}\\b`) })
}

describe('BoardPage', () => {
  it('shows every room by floor with its state, occupancy, arrival of the day and task', async () => {
    mockMe(supervisorMe())
    serveBoard()
    renderWithProviders(<BoardPage />)

    const first = await screen.findByRole('region', { name: /^Piso 1/ })
    const r101 = tile(first, '101')
    expect(r101).toHaveTextContent('Sucia')
    expect(r101).toHaveTextContent('Llega 15:00')
    expect(r101).toHaveTextContent('Salida · Pendiente')
    expect(r101).toHaveTextContent('Luz Marina Pérez')
    const r102 = tile(first, '102')
    expect(r102).toHaveTextContent('2 huéspedes')
    expect(r102).toHaveTextContent('Sin asignar')
    const second = screen.getByRole('region', { name: /^Piso 2/ })
    expect(tile(second, '201')).toHaveTextContent('Fuera de servicio')
    expect(tile(second, '202')).toHaveTextContent('Inspeccionada')
  })

  it('sums up the day: rooms by state, tasks done and the load of each housekeeper', async () => {
    mockMe(supervisorMe())
    serveBoard()
    renderWithProviders(<BoardPage />)

    const summary = await screen.findByRole('region', { name: 'Resumen del día' })
    expect(within(summary).getByRole('group', { name: 'Sucias' })).toHaveTextContent('2')
    expect(within(summary).getByRole('group', { name: 'Fuera de servicio' })).toHaveTextContent('1')
    expect(within(summary).getByText('2 de 5 tareas terminadas')).toBeInTheDocument()
    expect(within(summary).getByRole('progressbar', { name: 'Tareas terminadas' })).toHaveAttribute('aria-valuenow', '2')
    const load = within(summary).getByRole('listitem', { name: 'Luz Marina Pérez' })
    expect(load).toHaveTextContent('30 min de 7 h')
  })

  it('shares the pending tasks with one click', async () => {
    mockMe(supervisorMe())
    serveBoard()
    let called = false
    server.use(
      http.post('/api/v1/housekeeping/tasks/auto-assign/', () => {
        called = true
        return HttpResponse.json({
          business_date: '2026-09-25',
          assigned: 3,
          unassigned: 0,
          staff: [],
          overloaded: [],
          minutes_per_shift: 420,
        })
      }),
    )
    const { user } = renderWithProviders(<BoardPage />)

    await user.click(await screen.findByRole('button', { name: 'Auto-asignar' }))

    await waitFor(() => expect(called).toBe(true))
    expect(await screen.findByText('3 tareas asignadas')).toBeInTheDocument()
  })

  it('assigns a task to a housekeeper from the room panel', async () => {
    mockMe(supervisorMe())
    serveBoard()
    let body: unknown
    server.use(
      http.post('/api/v1/housekeeping/tasks/:id/assign/', async ({ params, request }) => {
        body = { id: params.id, ...((await request.json()) as object) }
        return HttpResponse.json(makeTask({ number: '102', kind: 'stayover' }))
      }),
    )
    const { user } = renderWithProviders(<BoardPage />)

    await user.click(tile(await screen.findByRole('region', { name: /^Piso 1/ }), '102'))
    const panel = await screen.findByRole('dialog', { name: 'Habitación 102' })
    await user.click(within(panel).getByRole('combobox', { name: 'Asignar a' }))
    await user.click(await screen.findByRole('option', { name: 'Rosa Díaz' }))

    await waitFor(() => expect(body).toEqual({ id: 'task-102', user_id: 'user-rosa' }))
  })

  it('changes the state of a room from its panel', async () => {
    mockMe(supervisorMe())
    serveBoard()
    let body: unknown
    server.use(
      http.post('/api/v1/housekeeping/rooms/:id/status/', async ({ params, request }) => {
        body = { id: params.id, ...((await request.json()) as object) }
        return HttpResponse.json({ id: params.id, number: '202', housekeeping_status: 'dirty' })
      }),
    )
    const { user } = renderWithProviders(<BoardPage />)

    await user.click(tile(await screen.findByRole('region', { name: /^Piso 2/ }), '202'))
    const panel = await screen.findByRole('dialog', { name: 'Habitación 202' })
    const states = within(panel).getByRole('group', { name: 'Estado de la habitación' })
    expect(within(states).getByRole('button', { name: 'Inspeccionada' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(within(states).getByRole('button', { name: 'Sucia' }))

    await waitFor(() => expect(body).toEqual({ id: 'room-202', housekeeping_status: 'dirty' }))
  })

  it('approves the inspection of a room', async () => {
    mockMe(supervisorMe())
    const inspection = makeTask({ number: '202', kind: 'inspection', assigned_to: null, estimated_minutes: 10 })
    const board = makeBoard()
    board.floors[1].rooms[1] = { ...board.floors[1].rooms[1], housekeeping_status: 'clean', tasks: [inspection] }
    serveBoard(board)
    let body: unknown
    server.use(
      http.post('/api/v1/housekeeping/tasks/:id/inspect/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...inspection, status: 'inspected' })
      }),
    )
    const { user } = renderWithProviders(<BoardPage />)

    await user.click(tile(await screen.findByRole('region', { name: /^Piso 2/ }), '202'))
    const panel = await screen.findByRole('dialog', { name: 'Habitación 202' })
    await user.click(within(panel).getByRole('button', { name: 'Aprobar inspección' }))

    await waitFor(() => expect(body).toEqual({ passed: true, notes: '' }))
  })

  it('shows only the rooms in the chosen state', async () => {
    mockMe(supervisorMe())
    serveBoard()
    const { user } = renderWithProviders(<BoardPage />)

    await screen.findByRole('region', { name: /^Piso 1/ })
    await user.click(screen.getByRole('radio', { name: /Sucias/ }))

    expect(screen.getByRole('button', { name: /Habitación 101\b/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Habitación 102\b/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /^Piso 2/ })).not.toBeInTheDocument()
  })

  it('gives housekeepers their rooms and no supervision tools', async () => {
    mockMe(housekeeperMe())
    serveBoard()
    const { user } = renderWithProviders(<BoardPage />)

    expect(await screen.findByRole('link', { name: 'Mis habitaciones' })).toHaveAttribute('href', '/app/housekeeping/mine')
    expect(screen.queryByRole('button', { name: 'Auto-asignar' })).not.toBeInTheDocument()
    await user.click(tile(screen.getByRole('region', { name: /^Piso 1/ }), '101'))
    const panel = await screen.findByRole('dialog', { name: 'Habitación 101' })
    const states = within(panel).getByRole('group', { name: 'Estado de la habitación' })
    expect(within(states).getAllByRole('button').map((button) => button.textContent)).toEqual(['Limpia', 'Sucia'])
    expect(within(panel).queryByRole('combobox', { name: 'Asignar a' })).not.toBeInTheDocument()
  })
})
