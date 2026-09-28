import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardWidget } from '@/app/extensions'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import TodayPage from '../pages/TodayPage'
import { deskMe, FRONT_DESK, makeBoard, makeRackRoom, makeReservation, makeRoomOption, makeRow, serveFolio } from './fixtures'

const extensions = vi.hoisted(() => ({ widgets: [] as DashboardWidget[] }))

vi.mock('@/app/extensions', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/extensions')>()
  return { ...actual, useWidgets: () => extensions.widgets }
})

const TODAY = '/api/v1/frontdesk/today/'

function serveBoard(board = makeBoard()) {
  let requests = 0
  server.use(
    http.get(TODAY, () => {
      requests += 1
      return HttpResponse.json(board)
    }),
  )
  return { requests: () => requests }
}

function renderToday(extraRoutes: { path: string; element: ReactNode }[] = []) {
  return renderWithProviders(<TodayPage />, { route: '/app', path: '/app', routes: extraRoutes })
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  extensions.widgets = []
  // 09:00 in Bogotá: morning at the desk (only the clock is faked, timers stay real)
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-01T14:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('TodayPage', () => {
  it('greets the desk and shows the day at a glance', async () => {
    mockMe(deskMe(FRONT_DESK))
    serveBoard()
    renderToday()

    expect(await screen.findByRole('heading', { name: 'Buenos días, Andrés', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('jueves 1 de octubre')).toBeInTheDocument()
    const figures = await screen.findByRole('region', { name: 'Cifras de hoy' })
    expect(within(figures).getByText('62,5%')).toBeInTheDocument()
    expect(within(figures).getByText('15 de 24 habitaciones')).toBeInTheDocument()
    expect(within(figures).getByRole('meter', { name: 'Llegadas: 1 de 4' })).toBeInTheDocument()
    expect(within(figures).getByRole('meter', { name: 'Salidas: 3 de 6' })).toBeInTheDocument()
    expect(within(figures).getByText('32 huéspedes')).toBeInTheDocument()
    expect(within(figures).getByText('$ 2.105.800')).toBeInTheDocument()
  })

  it('lists the arrivals with what each one needs, and the other lists behind tabs', async () => {
    mockMe(deskMe(FRONT_DESK))
    serveBoard(
      makeBoard({
        arrivals: [
          makeRow({ is_vip: true }),
          makeRow({ stay_id: 'stay-2', reservation_id: 'res-2', code: 'HT-UNASG1', guest_name: 'Ana Ruiz', room: null, room_id: null, room_status: null, ready: false, issues: ['unassigned'], eta: null }),
        ],
        departures: [
          makeRow({ stay_id: 'stay-3', reservation_id: 'res-3', code: 'HT-LEAVE1', guest_name: 'Pedro Díaz', status: 'checked_in', checkin: '2026-09-29', checkout: '2026-10-01', departs_today: true, balance_due: '154700.00', ready: false, issues: ['balance_due'] }),
        ],
      }),
    )
    const { user } = renderToday()

    const activity = await screen.findByRole('region', { name: 'Movimientos de hoy' })
    const valeria = await within(activity).findByRole('listitem', { name: /Valeria Mejía/ })
    expect(within(valeria).getByText('Lista')).toBeInTheDocument()
    expect(within(valeria).getByLabelText('Huésped VIP')).toBeInTheDocument()
    expect(within(valeria).getByRole('button', { name: 'Check-in' })).toBeInTheDocument()
    const ana = within(activity).getByRole('listitem', { name: /Ana Ruiz/ })
    expect(within(ana).getByText('Sin habitación')).toBeInTheDocument()

    await user.click(within(activity).getByRole('tab', { name: /Salidas/ }))
    const pedro = await within(activity).findByRole('listitem', { name: /Pedro Díaz/ })
    expect(within(pedro).getByText('Saldo pendiente')).toBeInTheDocument()
    expect(within(pedro).getByRole('button', { name: 'Check-out' })).toBeInTheDocument()
  })

  it('checks a guest in from the list in two clicks and refreshes the board', async () => {
    mockMe(deskMe(FRONT_DESK))
    const board = serveBoard()
    let checkedIn = false
    server.use(
      http.get('/api/v1/bookings/reservations/res-1/', () => HttpResponse.json(makeReservation())),
      http.get('/api/v1/bookings/stays/stay-1/room-options/', () => HttpResponse.json([makeRoomOption()])),
      http.get('/api/v1/frontdesk/reservations/res-1/online-checkin/', () =>
        HttpResponse.json({ reservation_id: 'res-1', status: null, completed_at: null }),
      ),
      http.post('/api/v1/bookings/stays/stay-1/check-in/', () => {
        checkedIn = true
        return HttpResponse.json(makeReservation({ status: 'checked_in' }))
      }),
    )
    serveFolio('res-1')
    const { user } = renderToday()

    const row = await screen.findByRole('listitem', { name: /Valeria Mejía/ })
    await user.click(within(row).getByRole('button', { name: 'Check-in' }))
    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    await user.click(await within(dialog).findByRole('button', { name: 'Confirmar check-in' }))

    await waitFor(() => expect(checkedIn).toBe(true))
    await waitFor(() => expect(board.requests()).toBeGreaterThan(1))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('the key rack books a free room and checks in the guest waiting for another', async () => {
    mockMe(deskMe(FRONT_DESK))
    serveBoard(
      makeBoard({
        rooms: [
          makeRackRoom({ arrival: { stay_id: 'stay-1', reservation_id: 'res-1', guest_name: 'Valeria Mejía', checkin: '2026-10-01', late: false } }),
          makeRackRoom({ id: 'room-201', number: '201', floor: '2', housekeeping_status: 'clean' }),
        ],
      }),
    )
    server.use(
      http.get('/api/v1/bookings/reservations/res-1/', () => HttpResponse.json(makeReservation())),
      http.get('/api/v1/bookings/stays/stay-1/room-options/', () => HttpResponse.json([])),
      http.get('/api/v1/frontdesk/reservations/res-1/online-checkin/', () =>
        HttpResponse.json({ reservation_id: 'res-1', status: null, completed_at: null }),
      ),
    )
    serveFolio('res-1')
    const { user, router } = renderToday([{ path: '/app/reservations/new', element: <p>asistente</p> }])

    const rack = await screen.findByRole('region', { name: 'Casillero de habitaciones' })
    await user.click(within(rack).getByRole('button', { name: /101.*llega Valeria Mejía/ }))
    expect(await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })).toBeInTheDocument()
    await user.keyboard('{Escape}')

    await user.click(within(rack).getByRole('button', { name: /201.*reservar/i }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/reservations/new'))
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      checkin: '2026-10-01',
      checkout: '2026-10-02',
      room_id: 'room-201',
      room_type_id: 'rt-dbl',
    })
  })

  it('tells the desk when the day was not closed and links to the night audit', async () => {
    mockMe(deskMe(['*']))
    serveBoard(makeBoard({ calendar_date: '2026-10-02', night_audit: { due: true, last_report: null } }))
    renderToday()

    const notice = await screen.findByRole('status', { name: 'Auditoría nocturna pendiente' })
    expect(within(notice).getByRole('link', { name: 'Ir a la auditoría' })).toHaveAttribute('href', '/app/night-audit')
  })

  it('shows the widgets other features put on the panel', async () => {
    mockMe(deskMe(FRONT_DESK))
    serveBoard()
    extensions.widgets = [
      { id: 'hk', order: 10, size: 'md', Component: () => <p>Limpieza: 12 de 18 listas</p> },
      { id: 'broken', order: 20, size: 'sm', Component: () => {
        throw new Error('widget roto')
      } },
    ]
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    renderToday()

    expect(await screen.findByText('Limpieza: 12 de 18 listas')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Buenos días, Andrés', level: 1 })).toBeInTheDocument()
  })

  it('sends housekeeping staff straight to their rooms', async () => {
    mockMe(deskMe(['housekeeping.view', 'housekeeping.work', 'inventory.view']))
    const board = serveBoard()
    const { router } = renderToday([{ path: '/app/housekeeping/mine', element: <p>mis habitaciones</p> }])

    expect(await screen.findByText('mis habitaciones')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/housekeeping/mine')
    expect(board.requests()).toBe(0)
  })
})
