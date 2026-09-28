import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import CalendarPage from '../pages/CalendarPage'
import { calendarMe, makeDetail, mockCalendarApi, mockPost } from './mocks'

function renderPage() {
  return renderWithProviders(<CalendarPage />, { route: '/app/calendar', path: '/app/calendar' })
}

async function openBar(user: ReturnType<typeof renderPage>['user'], name: RegExp) {
  await user.click(await screen.findByRole('button', { name }))
  return within(await screen.findByRole('dialog'))
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  localStorage.clear()
  mockMe(calendarMe())
})

describe('booking side panel', () => {
  it('opens with the booking summary and the actions the front desk can take', async () => {
    mockCalendarApi()
    const { user } = renderPage()

    const panel = await openBar(user, /^Laura Gómez/)
    expect(panel.getByRole('heading', { name: 'Laura Gómez' })).toBeInTheDocument()
    expect(panel.getByText('HT-LAURA1')).toBeInTheDocument()
    expect(panel.getByText('Confirmada')).toBeInTheDocument()
    expect(panel.getByText('mar 13 oct')).toBeInTheDocument() // arrival
    expect(panel.getByText('jue 15 oct')).toBeInTheDocument() // departure
    expect(panel.getByText('Hab. 101')).toBeInTheDocument()
    expect(panel.getByText('Teléfono')).toBeInTheDocument()
    // Money comes from the reservation detail.
    expect(await panel.findByText('$ 761.600')).toBeInTheDocument()
    expect(panel.getByText('$ 380.800')).toBeInTheDocument()

    expect(panel.getByRole('button', { name: 'Hacer check-in' })).toBeInTheDocument()
    expect(panel.getByRole('button', { name: 'Mover…' })).toBeInTheDocument()
    expect(panel.getByRole('button', { name: 'Quitar habitación' })).toBeInTheDocument()
    expect(panel.getByRole('link', { name: 'Abrir reserva' })).toHaveAttribute('href', '/app/reservations/res-laura')
    expect(panel.queryByRole('button', { name: 'Hacer check-out' })).not.toBeInTheDocument()
  })

  it('checks a guest in and says where they are', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/check-in/', () => {
      api.data.stays = api.data.stays.map((stay) => (stay.id === 'laura' ? { ...stay, status: 'checked_in' } : stay))
      const laura = api.data.stays.find((stay) => stay.id === 'laura')!
      return { status: 200, json: makeDetail(laura, api.data) }
    })
    const { user } = renderPage()

    const panel = await openBar(user, /^Laura Gómez/)
    await user.click(panel.getByRole('button', { name: 'Hacer check-in' }))

    expect(await screen.findByText('Check-in hecho: Laura Gómez en Hab. 101')).toBeInTheDocument()
    expect(api.posts).toEqual([{ path: '/api/v1/bookings/stays/laura/check-in/', body: { force: false } }])
    // The grid refetches: the bar now says the guest is in house.
    expect(await screen.findByRole('button', { name: /^Laura Gómez · HT-LAURA1 · En casa/ })).toBeInTheDocument()
  })

  it('explains a room that is not ready and can check in anyway', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/check-in/', (body) =>
      (body as { force: boolean }).force
        ? { status: 200, json: makeDetail(api.data.stays[0], api.data) }
        : {
            status: 409,
            json: { detail: 'La habitación no está lista', code: 'room_not_ready', room_id: 'room-101', housekeeping_status: 'dirty' },
          },
    )
    const { user } = renderPage()

    const panel = await openBar(user, /^Laura Gómez/)
    await user.click(panel.getByRole('button', { name: 'Hacer check-in' }))
    expect(await panel.findByText('La 101 está sucia.')).toBeInTheDocument()

    await user.click(panel.getByRole('button', { name: 'Hacer el check-in de todas formas' }))
    expect(await screen.findByText('Check-in hecho: Laura Gómez en Hab. 101')).toBeInTheDocument()
    expect(api.posts.map((post) => post.body)).toEqual([{ force: false }, { force: true }])
  })

  it('stops a check-out with a balance due, offering to collect or to leave anyway', async () => {
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/check-out/', (body) =>
      (body as { force: boolean }).force
        ? { status: 200, json: makeDetail(api.data.stays[1], api.data) }
        : { status: 409, json: { detail: 'La reserva tiene un saldo pendiente de 77350.00', code: 'balance_due', amount: '77350.00' } },
    )
    const { user } = renderPage()

    const panel = await openBar(user, /^Mateo Ruiz/)
    expect(panel.queryByRole('button', { name: 'Hacer check-in' })).not.toBeInTheDocument()
    await user.click(panel.getByRole('button', { name: 'Hacer check-out' }))

    expect(await panel.findByText('La reserva tiene un saldo pendiente de $ 77.350.')).toBeInTheDocument()
    expect(panel.getByRole('link', { name: 'Abrir la reserva para cobrar' })).toHaveAttribute('href', '/app/reservations/res-mateo')
    await user.click(panel.getByRole('button', { name: 'Salir con saldo pendiente' }))
    expect(await screen.findByText('Check-out hecho: Mateo Ruiz')).toBeInTheDocument()
    expect(api.posts.map((post) => post.body)).toEqual([{ force: false }, { force: true }])
  })

  it('only lets a front desk without the permission collect, not leave with a balance due', async () => {
    mockMe(calendarMe(['bookings.view', 'bookings.manage', 'bookings.checkin', 'rates.view']))
    const api = mockCalendarApi()
    mockPost(api, '/bookings/stays/:id/check-out/', () => ({
      status: 409,
      json: { detail: 'Saldo pendiente', code: 'balance_due', amount: '77350.00' },
    }))
    const { user } = renderPage()

    const panel = await openBar(user, /^Mateo Ruiz/)
    await user.click(panel.getByRole('button', { name: 'Hacer check-out' }))
    expect(await panel.findByRole('link', { name: 'Abrir la reserva para cobrar' })).toBeInTheDocument()
    expect(panel.queryByRole('button', { name: 'Salir con saldo pendiente' })).not.toBeInTheDocument()
  })

  it('is read-only for someone who can only look at bookings', async () => {
    mockMe(calendarMe(['bookings.view']))
    const api = mockCalendarApi()
    const { user } = renderPage()

    const panel = await openBar(user, /^Laura Gómez/)
    expect(panel.getByRole('link', { name: 'Abrir reserva' })).toBeInTheDocument()
    expect(panel.queryByRole('button', { name: 'Hacer check-in' })).not.toBeInTheDocument()
    expect(panel.queryByRole('button', { name: 'Mover…' })).not.toBeInTheDocument()
    expect(panel.queryByRole('button', { name: 'Quitar habitación' })).not.toBeInTheDocument()
    // Without `rates.view` the grid never asks for prices.
    await waitFor(() => expect(api.calendarRequests.length).toBeGreaterThan(0))
    expect(api.gridRequests).toHaveLength(0)
  })
})
