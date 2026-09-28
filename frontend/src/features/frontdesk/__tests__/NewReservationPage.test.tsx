import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import NewReservationPage from '../pages/NewReservationPage'
import { deskMe, FRONT_DESK, makeOffer, makeReservation, page } from './fixtures'

const guest = {
  id: 'guest-1',
  first_name: 'Laura',
  last_name: 'Gómez',
  full_name: 'Laura Gómez',
  email: 'laura@example.com',
  phone: '+573001234567',
  document_type: 'CC',
  document_number: '52123456',
  nationality: 'CO',
  country_of_residence: 'CO',
  city_of_residence: 'Cartagena',
  language: 'es',
  is_vip: false,
  blacklisted: false,
  tags: [],
  is_foreign_non_resident: false,
  anonymized_at: null,
  stays_count: 1,
  reservations_count: 1,
  last_stay_date: null,
  created_at: '2026-09-01T10:00:00-05:00',
}

const breakfast = {
  id: 'extra-brk',
  code: 'BRK',
  name: { es: 'Desayuno', en: 'Breakfast' },
  price: '35000.00',
  charge_type: 'per_person_night',
  tax: 'tax-extras',
  sellable_online: true,
  is_active: true,
}

interface Calls {
  offers: URLSearchParams[]
  created: Record<string, unknown>[]
  charges: unknown[]
  payments: unknown[]
  checkIns: string[]
}

function serve(): Calls {
  const calls: Calls = { offers: [], created: [], charges: [], payments: [], checkIns: [] }
  const created = makeReservation({ id: 'res-new', code: 'HT-NEW001', folio_id: 'folio-new' })
  server.use(
    http.get('/api/v1/bookings/offers/', ({ request }) => {
      calls.offers.push(new URL(request.url).searchParams)
      return HttpResponse.json([makeOffer()])
    }),
    http.get('/api/v1/rates/extras/', () => HttpResponse.json(page([breakfast]))),
    http.get('/api/v1/guests/guests/', () => HttpResponse.json(page([guest]))),
    http.get('/api/v1/guests/guests/lookup/', () => HttpResponse.json([])),
    http.get('/api/v1/finance/cash-shifts/current/', () => HttpResponse.json({ shift: null })),
    http.post('/api/v1/bookings/reservations/', async ({ request }) => {
      calls.created.push((await request.json()) as Record<string, unknown>)
      return HttpResponse.json(created, { status: 201 })
    }),
    http.post('/api/v1/finance/folios/folio-new/charges/', async ({ request }) => {
      calls.charges.push(await request.json())
      return HttpResponse.json({ id: 'charge-1' }, { status: 201 })
    }),
    http.post('/api/v1/finance/folios/folio-new/payments/', async ({ request }) => {
      calls.payments.push(await request.json())
      return HttpResponse.json({ id: 'payment-1' }, { status: 201 })
    }),
    http.post('/api/v1/bookings/stays/:id/check-in/', ({ params }) => {
      calls.checkIns.push(String(params.id))
      return HttpResponse.json(makeReservation({ id: 'res-new', status: 'checked_in' }))
    }),
  )
  return calls
}

function renderWizard(route = '/app/reservations/new?checkin=2026-10-01&checkout=2026-10-03') {
  return renderWithProviders(<NewReservationPage />, {
    route,
    path: '/app/reservations/new',
    routes: [{ path: '/app/reservations/:id', element: <p>detalle de la reserva</p> }],
  })
}

const step = (name: string) => screen.findByRole('heading', { name, level: 2 })
const next = () => screen.getByRole('button', { name: 'Continuar' })

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(deskMe(FRONT_DESK))
})

describe('NewReservationPage', () => {
  it('walks the five steps and creates the reservation, its extras and the payment', async () => {
    const calls = serve()
    const { user, router } = renderWizard()

    await step('Fechas y huéspedes')
    await user.click(next())

    await step('Tarifa')
    await user.click(await screen.findByRole('radio', { name: /Tarifa flexible/ }))
    expect(Object.fromEntries(calls.offers.at(-1)!)).toEqual({
      checkin: '2026-10-01',
      checkout: '2026-10-03',
      adults: '2',
      children: '0',
      channel: 'direct',
    })
    await user.click(next())

    await step('Huésped')
    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'laura')
    await user.click(await screen.findByRole('option', { name: /Laura Gómez/ }))
    await user.click(next())

    await step('Extras y notas')
    const extra = screen.getByRole('group', { name: 'Desayuno' })
    await user.click(within(extra).getByRole('button', { name: 'Agregar' }))
    expect(within(extra).getByRole('spinbutton', { name: 'Cantidad de Desayuno' })).toHaveValue(4)
    await user.type(screen.getByLabelText('Hora estimada de llegada'), '21:30')
    await user.click(next())

    await step('Garantía y pago')
    await user.click(screen.getByRole('radio', { name: 'Registrar un pago ahora' }))
    await user.click(screen.getByRole('radio', { name: 'Datáfono' }))
    await user.type(screen.getByRole('textbox', { name: 'Referencia' }), 'VOUCHER-7')
    await user.click(screen.getByRole('button', { name: 'Crear reserva' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app/reservations/res-new'))
    expect(calls.created).toEqual([
      {
        booker_id: 'guest-1',
        stays: [{ room_type_id: 'rt-dbl', rate_plan_id: 'plan-flex', checkin: '2026-10-01', checkout: '2026-10-03', adults: 2, children: 0, children_ages: [] }],
        source: 'front_desk',
        notes: '',
        special_requests: '',
        promo_code: '',
        language: 'es',
        eta: '21:30',
        status: 'confirmed',
        guarantee: 'deposit',
      },
    ])
    expect(calls.charges).toEqual([{ extra_id: 'extra-brk', quantity: 4 }])
    expect(calls.payments).toEqual([{ amount: '761600', method: 'card_terminal', reference: 'VOUCHER-7', notes: '' }])
    expect(calls.checkIns).toEqual([])
  })

  it('says what each step is missing before moving on', async () => {
    serve()
    const { user } = renderWizard()

    await step('Fechas y huéspedes')
    await user.click(screen.getByRole('button', { name: 'Agregar niño' }))
    await user.click(next())
    expect(await screen.findByText('Indica la edad de cada niño.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Fechas y huéspedes', level: 2 })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quitar niño' }))
    await user.click(next())
    await step('Tarifa')
    await screen.findByRole('radio', { name: /Tarifa flexible/ })
    await user.click(next())
    expect(await screen.findByText('Elige una tarifa para continuar.')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /Tarifa flexible/ }))
    await user.click(next())
    await step('Huésped')
    await user.click(next())
    expect(await screen.findByText('Elige o crea el huésped titular.')).toBeInTheDocument()
  })

  it('a walk-in arrives today and is checked in right after the reservation is created', async () => {
    const calls = serve()
    const { user, router } = renderWizard('/app/reservations/new?walk_in=1')

    await step('Fechas y huéspedes')
    expect(screen.getByRole('switch', { name: 'Llega ahora (walk-in)' })).toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Agregar noche' }))
    await user.click(next())

    await step('Tarifa')
    await user.click(await screen.findByRole('radio', { name: /Tarifa flexible/ }))
    expect(calls.offers.at(-1)!.get('checkout')).toBe('2026-10-03')
    await user.click(next())

    await step('Huésped')
    await user.type(screen.getByRole('combobox', { name: 'Buscar huésped' }), 'laura')
    await user.click(await screen.findByRole('option', { name: /Laura Gómez/ }))
    await user.click(next())
    await step('Extras y notas')
    await user.click(next())
    await step('Garantía y pago')
    await user.click(screen.getByRole('button', { name: 'Crear y hacer check-in' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app/reservations/res-new'))
    expect(calls.created[0]).toMatchObject({ source: 'walk_in', stays: [{ checkin: '2026-10-01', checkout: '2026-10-03' }] })
    expect(calls.checkIns).toEqual(['stay-1'])
  })
})
