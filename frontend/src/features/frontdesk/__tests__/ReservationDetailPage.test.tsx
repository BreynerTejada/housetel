import { screen, waitFor, within } from '@testing-library/react'
import { Send } from 'lucide-react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReservationAction, ReservationTab } from '@/app/extensions'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import ReservationDetailPage from '../pages/ReservationDetailPage'
import { deskMe, FRONT_DESK, makeReservation, makeRoomOption, makeStay } from './fixtures'

const extensions = vi.hoisted(() => ({
  tabs: [] as ReservationTab[],
  actions: [] as ReservationAction[],
}))

vi.mock('@/app/extensions', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/extensions')>()
  return { ...actual, useReservationTabs: () => extensions.tabs, useReservationActions: () => extensions.actions }
})

const DETAIL = '/api/v1/bookings/reservations/res-1/'

function serveReservation(...versions: ReturnType<typeof makeReservation>[]) {
  let current = 0
  server.use(http.get(DETAIL, () => HttpResponse.json(versions[Math.min(current, versions.length - 1)])))
  return { advance: () => (current += 1) }
}

function renderDetail() {
  return renderWithProviders(<ReservationDetailPage />, { route: '/app/reservations/res-1', path: '/app/reservations/:id' })
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  extensions.tabs = []
  extensions.actions = []
  mockMe(deskMe(FRONT_DESK))
})

describe('ReservationDetailPage', () => {
  it('shows who, when, where and how much at a glance', async () => {
    serveReservation(makeReservation())
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Valeria Mejía', level: 1 })).toBeInTheDocument()
    const header = screen.getByRole('region', { name: 'Reserva HT-7K2M9Q' })
    expect(within(header).getByText('HT-7K2M9Q')).toBeInTheDocument()
    expect(within(header).getByText('Confirmada')).toBeInTheDocument()
    expect(within(header).getByText('Teléfono')).toBeInTheDocument()
    expect(within(header).getByText('$ 761.600')).toBeInTheDocument()
    expect(within(header).getByText('Lista para check-in')).toBeInTheDocument()
    const stay = screen.getByRole('article', { name: /Estándar/ })
    expect(within(stay).getByText('Tarifa flexible')).toBeInTheDocument()
    expect(within(stay).getByText('101')).toBeInTheDocument()
  })

  it('renders the tabs other features register, with the reservation id', async () => {
    serveReservation(makeReservation())
    extensions.tabs = [
      { id: 'folio', labelKey: 'finance:tabs.folio', order: 20, Component: ({ reservationId }) => <p>Folio de {reservationId}</p> },
      { id: 'messages', labelKey: 'frontdesk:tabs.summary', order: 40, Component: () => <p>otra pestaña</p> },
    ]
    const { user } = renderDetail()

    const tabs = await screen.findByRole('tablist', { name: 'Secciones de la reserva' })
    expect(within(tabs).getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Resumen', 'Huéspedes', 'Folio', 'Resumen'])
    await user.click(within(tabs).getByRole('tab', { name: 'Folio' }))

    expect(await screen.findByText('Folio de res-1')).toBeInTheDocument()
  })

  it('runs the actions other features register in a dialog they can close', async () => {
    serveReservation(makeReservation())
    extensions.actions = [
      {
        id: 'send-link',
        labelKey: 'frontdesk:actions.newReservation',
        icon: Send,
        order: 10,
        Component: ({ reservationId, close }) => (
          <button type="button" onClick={close}>
            Enviar a {reservationId}
          </button>
        ),
      },
    ]
    const { user } = renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Más acciones' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Nueva reserva' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva reserva' })
    await user.click(within(dialog).getByRole('button', { name: 'Enviar a res-1' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('cancels with the penalty in view and a reason', async () => {
    const served = serveReservation(makeReservation(), makeReservation({ status: 'cancelled', cancellation_fee: '380800.00' }))
    let body: unknown
    server.use(
      http.get(`${DETAIL}cancel-preview/`, () =>
        HttpResponse.json({ fee: '380800.00', currency: 'COP', reason: 'first_night', free_until: '2026-09-29T15:00:00-05:00', non_refundable: false, policy: {} }),
      ),
      http.post(`${DETAIL}cancel/`, async ({ request }) => {
        body = await request.json()
        served.advance()
        return HttpResponse.json(makeReservation({ status: 'cancelled' }))
      }),
    )
    const { user } = renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Más acciones' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Cancelar reserva' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cancelar la reserva HT-7K2M9Q' })
    expect(await within(dialog).findByText(/Penalidad: \$ 380\.800/)).toBeInTheDocument()
    const confirm = within(dialog).getByRole('button', { name: 'Cancelar reserva' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByRole('textbox', { name: 'Motivo' }), 'Cambio de planes')
    await user.click(confirm)

    await waitFor(() => expect(body).toEqual({ reason: 'Cambio de planes', waive_fee: false, confirm: true }))
    expect(await screen.findByText('Cancelada')).toBeInTheDocument()
  })

  it('extends the stay one night after showing the new price', async () => {
    const served = serveReservation(makeReservation())
    let previewBody: unknown
    let modifyBody: unknown
    server.use(
      http.post('/api/v1/bookings/stays/stay-1/modify-preview/', async ({ request }) => {
        previewBody = await request.json()
        return HttpResponse.json({
          stay: { ...makeStay(), checkout_date: '2026-10-04', nights: 3, room_type_id: 'rt-dbl', rate_plan_id: 'plan-flex', room_id: 'room-101', bed_id: null, total_amount: '1142400.00' },
          room_kept: true,
          current_total: '761600.00',
          difference: '380800.00',
          reservation_total: '1142400.00',
          balance: '1142400.00',
        })
      }),
      http.post('/api/v1/bookings/stays/stay-1/modify/', async ({ request }) => {
        modifyBody = await request.json()
        served.advance()
        return HttpResponse.json(makeReservation({ checkout_date: '2026-10-04' }))
      }),
    )
    const { user } = renderDetail()

    const stay = await screen.findByRole('article', { name: /Estándar/ })
    await user.click(await within(stay).findByRole('button', { name: 'Modificar fechas' }))
    const dialog = await screen.findByRole('dialog', { name: 'Modificar fechas' })
    await user.click(within(dialog).getByRole('button', { name: 'Una noche más' }))

    expect(await within(dialog).findByText('+ $ 380.800')).toBeInTheDocument()
    expect(within(dialog).getByText('Conserva la habitación 101')).toBeInTheDocument()
    expect(previewBody).toEqual({ checkin: '2026-10-01', checkout: '2026-10-04', reprice: true })
    await user.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(modifyBody).toEqual({ checkin: '2026-10-01', checkout: '2026-10-04', reprice: true }))
  })

  it('moves the stay to another room', async () => {
    serveReservation(makeReservation())
    let assigned: unknown
    server.use(
      http.get('/api/v1/bookings/stays/stay-1/room-options/', () => HttpResponse.json([makeRoomOption()])),
      http.post('/api/v1/bookings/stays/stay-1/assign/', async ({ request }) => {
        assigned = await request.json()
        return HttpResponse.json(makeReservation({ stays: [makeStay({ room: { id: 'room-102', number: '102', floor: '1', housekeeping_status: 'clean' } })] }))
      }),
    )
    const { user } = renderDetail()

    const stay = await screen.findByRole('article', { name: /Estándar/ })
    await user.click(await within(stay).findByRole('button', { name: 'Cambiar habitación' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cambiar habitación' })
    await user.click(await within(dialog).findByRole('radio', { name: /102/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Asignar' }))

    await waitFor(() => expect(assigned).toEqual({ room_id: 'room-102', bed_id: null, force: false }))
  })

  it('lists the booker and adds a companion to a stay', async () => {
    const served = serveReservation(makeReservation())
    let added: unknown
    server.use(
      http.get('/api/v1/guests/guests/', () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [{ ...makeReservation().booker, id: 'guest-2', first_name: 'Tomás', last_name: 'Mejía', full_name: 'Tomás Mejía', city_of_residence: '', blacklisted: false, tags: [], anonymized_at: null, stays_count: 0, reservations_count: 0, last_stay_date: null, created_at: '2026-09-01T10:00:00-05:00' }],
        }),
      ),
      http.get('/api/v1/guests/guests/lookup/', () => HttpResponse.json([])),
      http.post('/api/v1/bookings/stays/stay-1/occupants/', async ({ request }) => {
        added = await request.json()
        served.advance()
        return HttpResponse.json(makeReservation())
      }),
    )
    const { user } = renderDetail()

    await user.click(await screen.findByRole('tab', { name: 'Huéspedes' }))
    expect(await screen.findByText('CC 52.123.456')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Agregar acompañante' }))
    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'tomas')
    await user.click(await screen.findByRole('option', { name: /Tomás Mejía/ }))
    await user.click(screen.getByRole('button', { name: 'Agregar a la estadía' }))

    await waitFor(() => expect(added).toEqual({ guest_id: 'guest-2' }))
  })
})
