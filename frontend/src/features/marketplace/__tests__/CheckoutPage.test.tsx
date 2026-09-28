import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { BookingRequest, BookingResult, CheckoutQuote, CheckoutRequest } from '../api'
import { goToPayment } from '../lib/navigation'
import CheckoutPage from '../pages/CheckoutPage'
import { BRK, DBL, FLEX, makeDetail, PUBLIC } from './fixtures'

vi.mock('../lib/navigation', () => ({ goToPayment: vi.fn() }))

const ROUTE = `/book/casa-aurora?checkin=2026-10-09&checkout=2026-10-11&adults=2&items=${DBL}:${FLEX}:1`

/** The quote the backend would give: 2 nights of 320.000 + 19 % IVA unless the guest is exempt. */
function quoteFor(body: CheckoutRequest): CheckoutQuote {
  const exempt = body.guest.nationality !== '' && body.guest.nationality !== 'CO' && body.guest.country_of_residence !== 'CO'
  const net = 640000
  const tax = exempt ? 0 : 121600
  const breakfast = body.extras.length ? 140000 + 26600 : 0
  const total = net + tax + breakfast
  return {
    property_slug: 'casa-aurora',
    via: body.via,
    checkin: body.checkin,
    checkout: body.checkout,
    nights: 2,
    currency: 'COP',
    tax_exempt: exempt,
    items: [
      {
        room_type_id: DBL,
        rate_plan_id: FLEX,
        room_type_name: { es: 'Estándar', en: 'Standard' },
        room_type_kind: 'private',
        rate_plan_name: { es: 'Tarifa flexible', en: 'Flexible rate' },
        meal_plan: 'room_only',
        quantity: 1,
        adults: 2,
        children: 0,
        units: 1,
        net: `${net}.00`,
        tax: `${tax}.00`,
        total: `${net + tax}.00`,
        discount: '0.00',
        deposit: '0.00',
        deposit_percent: '0.00',
        cancellation_policy: makeDetail().cancellation_policies[0]!,
      },
    ],
    extras: body.extras.length
      ? [
          {
            extra_id: BRK,
            code: 'BRK',
            name: { es: 'Desayuno', en: 'Breakfast' },
            charge_type: 'per_person_night',
            quantity: 4,
            unit_price: '35000.00',
            net: '140000.00',
            tax: '26600.00',
            total: '166600.00',
            tax_exempt: false,
          },
        ]
      : [],
    lodging_total: `${net + tax}.00`,
    extras_total: `${breakfast}.00`,
    tax_total: `${tax + (breakfast ? 26600 : 0)}.00`,
    discount_total: '0.00',
    total: `${total}.00`,
    deposit_total: '0.00',
    requires_payment: false,
    due_now: { pay_now: `${total}.00`, pay_at_hotel: '0.00' },
    payment_option: body.payment_option,
    amount_due_now: body.payment_option === 'pay_now' ? `${total}.00` : '0.00',
    promo: null,
    online_payments: true,
  }
}

function serve(book: (body: BookingRequest) => Response = () => HttpResponse.json(booked(), { status: 201 })) {
  const quotes: CheckoutRequest[] = []
  const bookings: BookingRequest[] = []
  server.use(
    http.get(`${PUBLIC}/properties/casa-aurora/`, () => HttpResponse.json(makeDetail())),
    http.post(`${PUBLIC}/checkout/quote/`, async ({ request }) => {
      const body = (await request.json()) as CheckoutRequest
      quotes.push(body)
      return HttpResponse.json(quoteFor(body))
    }),
    http.post(`${PUBLIC}/bookings/`, async ({ request }) => {
      const body = (await request.json()) as BookingRequest
      bookings.push(body)
      return book(body)
    }),
  )
  return { quotes, bookings }
}

function booked(overrides: Partial<BookingResult> = {}): BookingResult {
  return {
    reservation_code: 'HT-7K2M9Q',
    status: 'confirmed',
    via: 'marketplace',
    currency: 'COP',
    total: '761600.00',
    amount_due_now: '0.00',
    payment: null,
    hold_expires_at: null,
    portal_url: 'http://localhost:5173/g/abc',
    confirmation_path: '/booking/HT-7K2M9Q/confirmed',
    ...overrides,
  }
}

function renderCheckout() {
  return renderWithProviders(<CheckoutPage />, {
    route: ROUTE,
    path: '/book/:slug',
    routes: [
      { path: '/booking/:code/confirmed', element: <p>confirmación</p> },
      { path: '/hotel/:slug', element: <p>hotel</p> },
    ],
  })
}

/** The amount next to a label in the summary (`<dt>label</dt><dd>amount</dd>`). */
function amountOf(summary: HTMLElement, label: string): string {
  const text = within(summary).getByText(label, { selector: 'dt' }).parentElement!.querySelector('dd')!.textContent ?? ''
  return text.replace(/\s+/g, ' ')
}

async function pickCountry(user: ReturnType<typeof renderCheckout>['user'], label: string, country: string) {
  await user.click(screen.getByRole('combobox', { name: label }))
  await user.type(await screen.findByPlaceholderText('Buscar país…'), country)
  await user.click(await screen.findByRole('option', { name: new RegExp(country) }))
}

async function fillGuest(user: ReturnType<typeof renderCheckout>['user']) {
  await user.type(screen.getByLabelText('Nombre'), 'Laura')
  await user.type(screen.getByLabelText('Apellidos'), 'Gómez')
  await user.type(screen.getByLabelText('Correo electrónico'), 'laura@example.com')
  await user.type(screen.getByLabelText('Celular'), '+57 300 123 4567')
  await pickCountry(user, 'Nacionalidad', 'Colombia')
  await pickCountry(user, 'País donde vives', 'Colombia')
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  sessionStorage.clear()
  vi.mocked(goToPayment).mockReset()
})

describe('CheckoutPage', () => {
  it('prices the selection with the IVA of lodging', async () => {
    serve()
    renderCheckout()

    const summary = await screen.findByRole('complementary', { name: 'Resumen de tu reserva' })
    await waitFor(() => expect(amountOf(summary, 'Total')).toBe('$ 761.600'))
    expect(amountOf(summary, 'IVA')).toBe('$ 121.600')
    expect(screen.getByText('El alojamiento incluye el IVA del 19 %. Si eres extranjero y no vives en Colombia, indícalo arriba y lo descontamos.')).toBeInTheDocument()
  })

  it('does not book until the guest details and the data authorization are complete', async () => {
    const { bookings } = serve()
    const { user } = renderCheckout()

    await user.click(await screen.findByRole('button', { name: 'Confirmar reserva' }))

    expect(await screen.findAllByText('Este campo es obligatorio')).not.toHaveLength(0)
    expect(screen.getByText('Necesitamos tu autorización para gestionar la reserva.')).toBeInTheDocument()
    expect(screen.getByLabelText('Nombre')).toHaveAttribute('aria-invalid', 'true')

    await user.type(screen.getByLabelText('Correo electrónico'), 'no-es-correo')
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }))
    expect(await screen.findByText('Escribe un correo válido')).toBeInTheDocument()
    expect(bookings).toHaveLength(0)
  })

  it('takes the IVA off as soon as the guest is a foreigner who does not live in Colombia', async () => {
    const { quotes } = serve()
    const { user } = renderCheckout()
    const summary = await screen.findByRole('complementary', { name: 'Resumen de tu reserva' })
    await waitFor(() => expect(amountOf(summary, 'Total')).toBe('$ 761.600'))

    // a foreign nationality without a residence yet already counts as non-resident (same rule as the backend)
    await pickCountry(user, 'Nacionalidad', 'Estados Unidos')
    expect(await screen.findByText('Exento de IVA de alojamiento')).toBeInTheDocument()
    await pickCountry(user, 'País donde vives', 'Estados Unidos')

    await waitFor(() => expect(amountOf(summary, 'Total')).toBe('$ 640.000'))
    expect(amountOf(summary, 'IVA')).toBe('$ 0')
    expect(within(summary).getByText('IVA de alojamiento exento')).toBeInTheDocument()
    expect(quotes.at(-1)!.guest).toEqual({ nationality: 'US', country_of_residence: 'US' })

    // living in Colombia brings the IVA back
    await pickCountry(user, 'País donde vives', 'Colombia')
    await waitFor(() => expect(amountOf(summary, 'Total')).toBe('$ 761.600'))
    expect(screen.queryByText('Exento de IVA de alojamiento')).not.toBeInTheDocument()
  })

  it('adds an extra to the quote and the booking', async () => {
    const { quotes } = serve()
    const { user } = renderCheckout()

    await user.click(await screen.findByRole('checkbox', { name: /Desayuno/ }))

    const summary = screen.getByRole('complementary', { name: 'Resumen de tu reserva' })
    await waitFor(() => expect(amountOf(summary, 'Total')).toBe('$ 928.200'))
    expect(quotes.at(-1)!.extras).toEqual([{ extra_id: BRK, quantity: null }])
  })

  it('books paying now and sends the guest to the payment gateway', async () => {
    const { bookings } = serve(() =>
      HttpResponse.json(
        booked({
          status: 'tentative',
          amount_due_now: '761600.00',
          payment: { checkout_url: 'http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD', reference: 'HT-7K2M9Q-AB12CD', amount: '761600.00', expires_at: null },
        }),
        { status: 201 },
      ),
    )
    const { user } = renderCheckout()
    await screen.findByRole('complementary', { name: 'Resumen de tu reserva' })

    await fillGuest(user)
    await user.click(screen.getByRole('radio', { name: /Pagar ahora/ }))
    await user.click(screen.getByRole('checkbox', { name: /Autorizo a Hotel Casa Aurora/ }))
    await user.click(await screen.findByRole('button', { name: 'Reservar y pagar $ 761.600' }))

    await waitFor(() => expect(goToPayment).toHaveBeenCalledWith('http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD'))
    expect(bookings[0]).toMatchObject({
      property_slug: 'casa-aurora',
      via: 'marketplace',
      checkin: '2026-10-09',
      checkout: '2026-10-11',
      items: [{ room_type_id: DBL, rate_plan_id: FLEX, quantity: 1, adults: 2, children: 0, children_ages: [] }],
      payment_option: 'pay_now',
      language: 'es',
      guest: {
        first_name: 'Laura',
        last_name: 'Gómez',
        email: 'laura@example.com',
        phone: '+57 300 123 4567',
        nationality: 'CO',
        country_of_residence: 'CO',
        data_processing_consent: true,
        marketing_consent: false,
      },
    })
    // the confirmation page (after the gateway) opens the booking with this email
    expect(sessionStorage.getItem('housetel.booking.HT-7K2M9Q')).toBe('laura@example.com')
  })

  it('books paying at the hotel and opens the confirmation', async () => {
    serve()
    const { user, router } = renderCheckout()
    await screen.findByRole('complementary', { name: 'Resumen de tu reserva' })

    await fillGuest(user)
    await user.click(screen.getByRole('checkbox', { name: /Autorizo a Hotel Casa Aurora/ }))
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/booking/HT-7K2M9Q/confirmed'))
    expect(goToPayment).not.toHaveBeenCalled()
  })

  it('explains that the rooms were taken in the meantime', async () => {
    serve(() => HttpResponse.json({ detail: 'Ya no hay disponibilidad para tu selección', code: 'no_availability' }, { status: 409 }))
    const { user } = renderCheckout()
    await screen.findByRole('complementary', { name: 'Resumen de tu reserva' })

    await fillGuest(user)
    await user.click(screen.getByRole('checkbox', { name: /Autorizo a Hotel Casa Aurora/ }))
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }))

    expect(await screen.findByText('Ya no hay disponibilidad para tu selección')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Elegir de nuevo' })).toHaveAttribute('href', '/hotel/casa-aurora?checkin=2026-10-09&checkout=2026-10-11&adults=2')
  })
})
