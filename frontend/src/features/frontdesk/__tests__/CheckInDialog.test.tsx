import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { CheckInDialog } from '../components/CheckInDialog'
import { deskMe, FRONT_DESK, makeReservation, makeRoomOption, makeStay, serveFolio } from './fixtures'

const RESERVATION = '/api/v1/bookings/reservations/res-1/'
const OPTIONS = '/api/v1/bookings/stays/stay-1/room-options/'
const ONLINE = '/api/v1/frontdesk/reservations/res-1/online-checkin/'

interface Calls {
  assign: unknown[]
  checkIn: unknown[]
}

function serve({
  reservation = makeReservation(),
  options = [makeRoomOption()],
  online = { reservation_id: 'res-1', status: 'completed', completed_at: '2026-09-30T18:02:00-05:00' },
  checkIn = () => HttpResponse.json(makeReservation({ status: 'checked_in' })),
}: {
  reservation?: ReturnType<typeof makeReservation>
  options?: ReturnType<typeof makeRoomOption>[]
  online?: { reservation_id: string; status: string | null; completed_at: string | null }
  checkIn?: () => Response
} = {}): Calls {
  const calls: Calls = { assign: [], checkIn: [] }
  server.use(
    http.get(RESERVATION, () => HttpResponse.json(reservation)),
    http.get(OPTIONS, () => HttpResponse.json(options)),
    http.get(ONLINE, () => HttpResponse.json(online)),
    http.post('/api/v1/bookings/stays/stay-1/assign/', async ({ request }) => {
      calls.assign.push(await request.json())
      return HttpResponse.json(reservation)
    }),
    http.post('/api/v1/bookings/stays/stay-1/check-in/', async ({ request }) => {
      calls.checkIn.push(await request.json())
      return checkIn()
    }),
  )
  serveFolio('res-1')
  return calls
}

function open(onDone = vi.fn()) {
  const view = renderWithProviders(<CheckInDialog open onOpenChange={() => undefined} stayId="stay-1" reservationId="res-1" onDone={onDone} />)
  return { ...view, onDone }
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(deskMe(FRONT_DESK))
})

describe('CheckInDialog', () => {
  it('checks in a guest whose clean room is waiting, after showing who they are', async () => {
    const calls = serve()
    const { user, onDone } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    expect(await within(dialog).findByText('CC 52.123.456')).toBeInTheDocument()
    expect(within(dialog).getByText('Check-in online completado')).toBeInTheDocument()
    const rooms = within(dialog).getByRole('radiogroup', { name: 'Habitación' })
    expect(within(rooms).getByRole('radio', { name: /101/ })).toBeChecked()
    expect(within(rooms).getByRole('radio', { name: /101/ })).toHaveAccessibleName(/Limpia/)
    expect(await within(dialog).findByText('Saldo por cobrar')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-in' }))

    await waitFor(() => expect(calls.checkIn).toEqual([{ force: false }]))
    expect(calls.assign).toEqual([])
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
  })

  it('offers the clean rooms of its category first when the assigned one is dirty', async () => {
    const calls = serve({
      reservation: makeReservation({ stays: [makeStay({ room: { id: 'room-101', number: '101', floor: '1', housekeeping_status: 'dirty' } })] }),
      options: [
        makeRoomOption({ room_id: 'room-103', room_number: '103', housekeeping_status: 'dirty', ready: false }),
        makeRoomOption({ room_id: 'room-301', room_number: '301', room_type_id: 'rt-ste', room_type_code: 'STE', housekeeping_status: 'inspected', same_category: false }),
        makeRoomOption({ room_id: 'room-102', room_number: '102' }),
      ],
    })
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    expect(await within(dialog).findByText(/La 101 está sucia/)).toBeInTheDocument()
    const rooms = within(dialog).getByRole('radiogroup', { name: 'Habitación' })
    expect(within(rooms).getAllByRole('radio').map((radio) => radio.getAttribute('data-room'))).toEqual(['101', '102', '103', '301'])
    // the first clean room of its category is proposed
    expect(within(rooms).getByRole('radio', { name: /102/ })).toBeChecked()

    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-in' }))

    await waitFor(() => expect(calls.checkIn).toEqual([{ force: false }]))
    expect(calls.assign).toEqual([{ room_id: 'room-102', bed_id: null, force: false }])
  })

  it('can still check in to the dirty room, saying so on the button', async () => {
    const calls = serve({
      reservation: makeReservation({ stays: [makeStay({ room: { id: 'room-101', number: '101', floor: '1', housekeeping_status: 'dirty' } })] }),
      options: [makeRoomOption({ room_id: 'room-102', room_number: '102' })],
    })
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    await user.click(await within(dialog).findByRole('radio', { name: /101/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Hacer check-in igual' }))

    await waitFor(() => expect(calls.checkIn).toEqual([{ force: true }]))
    expect(calls.assign).toEqual([])
  })

  it('moving to a room of another category is an upgrade', async () => {
    const calls = serve({
      options: [makeRoomOption({ room_id: 'room-301', room_number: '301', room_type_id: 'rt-ste', room_type_code: 'STE', same_category: false })],
    })
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    await user.click(await within(dialog).findByRole('radio', { name: /301/ }))
    expect(within(dialog).getByRole('radio', { name: /301/ })).toHaveAccessibleName(/Otra categoría/)
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-in' }))

    await waitFor(() => expect(calls.assign).toEqual([{ room_id: 'room-301', bed_id: null, force: true }]))
    expect(calls.checkIn).toEqual([{ force: false }])
  })

  it('a late arrival needs an explicit late check-in', async () => {
    const calls = serve({
      reservation: makeReservation({ checkin_date: '2026-09-30', stays: [makeStay({ checkin_date: '2026-09-30' })] }),
    })
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    expect(await within(dialog).findByText(/Llegaba el 30 sep/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Hacer check-in igual' }))

    await waitFor(() => expect(calls.checkIn).toEqual([{ force: true }]))
  })

  it('warns when the guest document is missing and keeps the dialog open on errors', async () => {
    serve({
      reservation: makeReservation({ booker: { ...makeReservation().booker, document_type: '', document_number: '' } }),
      online: { reservation_id: 'res-1', status: null, completed_at: null },
      checkIn: () =>
        HttpResponse.json(
          { detail: 'La habitación 101 no está lista (Sucia)', code: 'room_not_ready', room_id: 'room-101', housekeeping_status: 'dirty' },
          { status: 409 },
        ),
    })
    const { user, onDone } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-in de Valeria Mejía' })
    expect(await within(dialog).findByText(/Falta el documento/)).toBeInTheDocument()
    expect(within(dialog).getByText('Check-in online sin iniciar')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-in' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('La habitación 101 no está lista (Sucia)')
    expect(onDone).not.toHaveBeenCalled()
  })
})
