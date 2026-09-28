import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { CheckOutDialog } from '../components/CheckOutDialog'
import { deskMe, FRONT_DESK, makeFolio, makeReservation, makeStay, serveFolio } from './fixtures'

const RESERVATION = '/api/v1/bookings/reservations/res-1/'

const inHouse = (overrides: Parameters<typeof makeReservation>[0] = {}) =>
  makeReservation({
    status: 'checked_in',
    checkin_date: '2026-09-29',
    checkout_date: '2026-10-01',
    stays: [makeStay({ status: 'checked_in', checkin_date: '2026-09-29', checkout_date: '2026-10-01', nights: 2 })],
    ...overrides,
  })

function serve(versions: ReturnType<typeof makeReservation>[], onCheckOut: (body: unknown) => void = () => undefined) {
  let current = 0
  const bodies: unknown[] = []
  server.use(
    http.get(RESERVATION, () => HttpResponse.json(versions[Math.min(current, versions.length - 1)])),
    http.post('/api/v1/bookings/stays/stay-1/check-out/', async ({ request }) => {
      const body = await request.json()
      bodies.push(body)
      onCheckOut(body)
      return HttpResponse.json(inHouse({ status: 'checked_out' }))
    }),
  )
  return { bodies, advance: () => (current += 1) }
}

function open(onDone = vi.fn()) {
  const view = renderWithProviders(<CheckOutDialog open onOpenChange={() => undefined} stayId="stay-1" reservationId="res-1" onDone={onDone} />)
  return { ...view, onDone }
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

describe('CheckOutDialog', () => {
  it('checks out a guest whose account is settled', async () => {
    mockMe(deskMe(FRONT_DESK))
    const served = serve([inHouse({ balance: '0.00' })])
    serveFolio('res-1', makeFolio({ totals: { ...makeFolio().totals, reservation_balance: '0.00' } }))
    const { user, onDone } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-out de Valeria Mejía' })
    expect(await within(dialog).findByText('Cuenta saldada')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-out' }))

    await waitFor(() => expect(served.bodies).toEqual([{ force: false }]))
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
  })

  it('will not check out with a balance due unless the role allows it', async () => {
    mockMe(deskMe(FRONT_DESK))
    serve([inHouse({ balance: '154700.00' })])
    serveFolio('res-1')
    open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-out de Valeria Mejía' })
    expect(await within(dialog).findByText(/Queda un saldo de \$ 154\.700/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Confirmar check-out' })).toBeDisabled()
    expect(within(dialog).queryByRole('checkbox', { name: /saldo pendiente/ })).not.toBeInTheDocument()
  })

  it('a manager may check out with the balance still due', async () => {
    mockMe(deskMe(['*']))
    const served = serve([inHouse({ balance: '154700.00' })])
    serveFolio('res-1')
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-out de Valeria Mejía' })
    const confirm = await within(dialog).findByRole('button', { name: 'Confirmar check-out' })
    expect(confirm).toBeDisabled()
    await user.click(within(dialog).getByRole('checkbox', { name: /saldo pendiente/ }))
    await user.click(confirm)

    await waitFor(() => expect(served.bodies).toEqual([{ force: true }]))
  })

  it('collecting the balance in the folio unlocks the check-out', async () => {
    mockMe(deskMe(FRONT_DESK))
    const served = serve([inHouse({ balance: '483300.00' }), inHouse({ balance: '0.00' })])
    serveFolio('res-1')
    server.use(
      http.post('/api/v1/finance/folios/:id/payments/', () => {
        served.advance()
        return HttpResponse.json({ id: 'payment-2' }, { status: 201 })
      }),
    )
    const { user } = open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-out de Valeria Mejía' })
    await user.click(await within(dialog).findByRole('button', { name: 'Registrar pago' }))
    const payment = await screen.findByRole('dialog', { name: 'Registrar pago' })
    await user.click(within(payment).getByRole('radio', { name: 'Datáfono' }))
    await user.type(within(payment).getByLabelText('Número de voucher'), 'VOUCHER-9')
    await user.click(within(payment).getByRole('button', { name: 'Registrar pago' }))

    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Confirmar check-out' })).toBeEnabled())
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar check-out' }))
    await waitFor(() => expect(served.bodies).toEqual([{ force: false }]))
  })

  it('an early departure says how many nights are released', async () => {
    mockMe(deskMe(FRONT_DESK))
    serve([
      inHouse({
        balance: '0.00',
        checkout_date: '2026-10-04',
        stays: [makeStay({ status: 'checked_in', checkin_date: '2026-09-29', checkout_date: '2026-10-04', nights: 5 })],
      }),
    ])
    serveFolio('res-1')
    open()

    const dialog = await screen.findByRole('dialog', { name: 'Check-out de Valeria Mejía' })
    expect(await within(dialog).findByText(/Salida anticipada: se liberan 3 noches/)).toBeInTheDocument()
  })
})
