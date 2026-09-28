import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { BookingStatus } from '../api'
import { goToPayment } from '../lib/navigation'
import { rememberBookingEmail } from '../lib/storage'
import ConfirmationPage from '../pages/ConfirmationPage'
import { PUBLIC } from './fixtures'

vi.mock('../lib/navigation', () => ({ goToPayment: vi.fn() }))

const CODE = 'HT-7K2M9Q'
const REF = 'HT-7K2M9Q-AB12CD'

function booking(overrides: Partial<BookingStatus> = {}): BookingStatus {
  return {
    code: CODE,
    status: 'confirmed',
    via: 'marketplace',
    property: {
      slug: 'casa-aurora',
      name: 'Hotel Casa Aurora',
      city: 'Cartagena',
      address: 'Calle del Cuartel #36-77',
      phone: '+57 605 660 1234',
      email: 'reservas@casaaurora.co',
      timezone: 'America/Bogota',
      check_in_time: '15:00',
      check_out_time: '12:00',
      primary_color: '#0E6E74',
      logo: '',
    },
    checkin: '2026-10-09',
    checkout: '2026-10-11',
    nights: 2,
    adults: 2,
    children: 0,
    currency: 'COP',
    booker: { first_name: 'Laura', last_name: 'Gómez', email: 'laura@example.com' },
    rooms: [
      {
        room_type_name: { es: 'Estándar', en: 'Standard' },
        room_type_kind: 'private',
        rate_plan_name: { es: 'Tarifa flexible', en: 'Flexible rate' },
        meal_plan: 'room_only',
        units: 1,
        adults: 2,
        children: 0,
        total: '761600.00',
      },
    ],
    extras: [],
    total: '761600.00',
    paid: '0.00',
    balance: '761600.00',
    tax_exempt: false,
    cancellation_policy: {
      name: { es: 'Flexible 48h' },
      description: {},
      non_refundable: false,
      free_until_hours_before: 48,
      penalty_type: 'first_night',
      penalty_value: '0.00',
    },
    hold_expires_at: null,
    special_requests: '',
    eta: null,
    payment: null,
    portal_url: 'http://localhost:5173/g/abc',
    confirmation_path: `/booking/${CODE}/confirmed`,
    created_at: '2026-10-01T09:00:00-05:00',
    ...overrides,
  }
}

function serveLookup(respond: (email: string) => Response) {
  const emails: string[] = []
  server.use(
    http.get(`${PUBLIC}/bookings/${CODE}/`, ({ request }) => {
      const email = new URL(request.url).searchParams.get('email') ?? ''
      emails.push(email)
      return respond(email)
    }),
  )
  return emails
}

function renderPage(search = '') {
  return renderWithProviders(<ConfirmationPage />, { route: `/booking/${CODE}/confirmed${search}`, path: '/booking/:code/confirmed' })
}

beforeEach(() => {
  sessionStorage.clear()
  vi.mocked(goToPayment).mockReset()
})

describe('ConfirmationPage', () => {
  it('shows a booking paid at the hotel as confirmed, with the portal and its details', async () => {
    rememberBookingEmail(CODE, 'laura@example.com')
    const emails = serveLookup(() => HttpResponse.json(booking()))
    renderPage()

    expect(await screen.findByRole('heading', { level: 1, name: 'Tu reserva está confirmada' })).toBeInTheDocument()
    expect(screen.getByText(CODE)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir mi reserva' })).toHaveAttribute('href', 'http://localhost:5173/g/abc')
    expect(screen.getByText('Saldo a pagar en el hotel')).toBeInTheDocument()
    expect(screen.getByText('Cancelación gratis hasta 2 días antes de la llegada')).toBeInTheDocument()
    expect(emails).toEqual(['laura@example.com'])
  })

  it('confirms the booking once the gateway approves the payment', async () => {
    rememberBookingEmail(CODE, 'laura@example.com')
    let confirmed = false
    serveLookup(() =>
      HttpResponse.json(
        confirmed
          ? booking({ paid: '761600.00', balance: '0.00', payment: { reference: REF, status: 'approved', amount: '761600.00', checkout_url: null, expires_at: null } })
          : booking({
              status: 'tentative',
              hold_expires_at: '2026-10-01T09:45:00-05:00',
              payment: { reference: REF, status: 'pending', amount: '761600.00', checkout_url: `http://localhost:5173/sim/pay/${REF}`, expires_at: null },
            }),
      ),
    )
    server.use(
      http.get(`/api/v1/public/finance/intents/${REF}/status/`, () => {
        confirmed = true // the approved payment confirms the reservation (bookings' receiver)
        return HttpResponse.json({ reference: REF, status: 'approved', paid: true, amount: '761600.00', currency: 'COP', method: 'wompi_pse', reservation_code: CODE, property_slug: 'casa-aurora' })
      }),
    )
    renderPage(`?payment_ref=${REF}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'Tu reserva está confirmada' })).toBeInTheDocument()
    expect(screen.getByText('Pagado')).toBeInTheDocument()
  })

  it('offers to try again when the payment was declined', async () => {
    rememberBookingEmail(CODE, 'laura@example.com')
    serveLookup(() =>
      HttpResponse.json(
        booking({
          status: 'tentative',
          payment: { reference: REF, status: 'declined', amount: '761600.00', checkout_url: `http://localhost:5173/sim/pay/${REF}`, expires_at: null },
        }),
      ),
    )
    server.use(
      http.get(`/api/v1/public/finance/intents/${REF}/status/`, () =>
        HttpResponse.json({ reference: REF, status: 'declined', paid: false, amount: '761600.00', currency: 'COP', method: 'wompi_card', reservation_code: CODE, property_slug: 'casa-aurora' }),
      ),
    )
    const { user } = renderPage(`?payment_ref=${REF}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'El pago no fue aprobado' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Intentar de nuevo' }))
    expect(goToPayment).toHaveBeenCalledWith(`http://localhost:5173/sim/pay/${REF}`)
  })

  it('asks for the email when the page does not know it, and never shows a booking to the wrong email', async () => {
    serveLookup((email) =>
      email === 'laura@example.com'
        ? HttpResponse.json(booking())
        : HttpResponse.json({ detail: 'No encontramos una reserva con ese código y ese correo', code: 'not_found' }, { status: 404 }),
    )
    const { user } = renderPage()

    expect(screen.getByRole('heading', { name: 'Abre tu reserva' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Correo electrónico'), 'otra@example.com')
    await user.click(screen.getByRole('button', { name: 'Ver mi reserva' }))
    expect(await screen.findByText('No encontramos una reserva con ese código y ese correo.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Correo electrónico'))
    await user.type(screen.getByLabelText('Correo electrónico'), 'laura@example.com')
    await user.click(screen.getByRole('button', { name: 'Ver mi reserva' }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Tu reserva está confirmada' })).toBeInTheDocument())
  })
})
