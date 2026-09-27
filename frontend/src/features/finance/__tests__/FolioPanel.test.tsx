import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { FolioPanel } from '../components/FolioPanel'
import { FOLIO_ID, makeFolio, makeIntent, makePayment, RESERVATION_ID, summaryOf } from './fixtures'
import type { FolioDetail } from '../api'

const LIST = '/api/v1/finance/folios/'
const DETAIL = `/api/v1/finance/folios/${FOLIO_ID}/`

function serveFolio(...versions: FolioDetail[]) {
  let current = 0
  const reservations: string[] = []
  server.use(
    http.get(LIST, ({ request }) => {
      reservations.push(new URL(request.url).searchParams.get('reservation') ?? '')
      const folio = versions[Math.min(current, versions.length - 1)]!
      return HttpResponse.json({ count: 1, next: null, previous: null, results: [summaryOf(folio)] })
    }),
    http.get(DETAIL, () => HttpResponse.json(versions[Math.min(current, versions.length - 1)])),
  )
  return {
    reservations,
    advance: () => {
      current += 1
    },
  }
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

describe('FolioPanel', () => {
  it('shows what the guest owes, how much is paid and every line', async () => {
    mockMe(makeMe())
    const served = serveFolio(makeFolio())

    renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    expect(await screen.findByText('$ 483.300')).toBeInTheDocument()
    expect(screen.getByText('Saldo por cobrar')).toBeInTheDocument()
    expect(screen.getByText('Pagado $ 300.000 de $ 783.300')).toBeInTheDocument()
    expect(served.reservations).toContain(RESERVATION_ID)
    const breakfast = screen.getByRole('row', { name: /Desayuno/ })
    expect(within(breakfast).getByText('$ 83.300')).toBeInTheDocument()
    const minibar = screen.getByRole('row', { name: /Minibar/ })
    expect(within(minibar).getByText('Anulado')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: /VOUCHER-1/ })).getByText('Datáfono')).toBeInTheDocument()
  })

  it('records a manual payment and shows the settled account', async () => {
    mockMe(makeMe())
    const served = serveFolio(
      makeFolio(),
      makeFolio({ totals: { ...makeFolio().totals, payments_total: '783300.00', balance: '-350000.00', reservation_balance: '0.00' } }),
    )
    let body: Record<string, unknown> | undefined
    server.use(
      http.post(`${DETAIL}payments/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        served.advance()
        return HttpResponse.json({ id: 'payment-2' }, { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Registrar pago' }))
    const dialog = await screen.findByRole('dialog', { name: 'Registrar pago' })
    expect(within(dialog).getByLabelText('Monto')).toHaveValue('483.300')
    await user.click(within(dialog).getByRole('radio', { name: 'Datáfono' }))
    await user.type(within(dialog).getByLabelText('Número de voucher'), 'VOUCHER-9')
    await user.click(within(dialog).getByRole('button', { name: 'Registrar pago' }))

    await waitFor(() => expect(body).toBeDefined())
    expect({ ...body, amount: Number(body!.amount) }).toEqual({
      amount: 483300,
      method: 'card_terminal',
      reference: 'VOUCHER-9',
      notes: '',
    })
    expect(await screen.findByText('Cuenta saldada')).toBeInTheDocument()
  })

  it('warns before taking cash without an open cash shift', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    server.use(http.get('/api/v1/finance/cash-shifts/current/', () => HttpResponse.json({ shift: null })))
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Registrar pago' }))
    const dialog = await screen.findByRole('dialog', { name: 'Registrar pago' })
    await user.click(within(dialog).getByRole('radio', { name: 'Efectivo' }))

    expect(await within(dialog).findByText(/Abre tu turno de caja/)).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'Ir a Caja' })).toHaveAttribute('href', '/app/cashier')
  })

  it('voids a charge only after the amount is typed', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    let body: Record<string, unknown> | undefined
    server.use(
      http.post('/api/v1/finance/charges/charge-2/void/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 'charge-2', voided: true })
      }),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Acciones de «Desayuno»' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Anular cargo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Anular cargo' })
    const confirm = within(dialog).getByRole('button', { name: 'Anular cargo' })
    await user.type(within(dialog).getByLabelText('Motivo'), 'Cargado por error')
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Texto de confirmación'), '83.300')
    await user.click(confirm)

    await waitFor(() => expect(body).toEqual({ reason: 'Cargado por error', confirm: true }))
  })

  it('warns that voiding a room night does not lower what the reservation owes', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Acciones de «Noche · Estándar»' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Anular cargo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Anular cargo' })

    expect(within(dialog).getByText(/no cambia el saldo de la reserva/)).toBeInTheDocument()
  })

  it('refunds after typing the amount being returned', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    let body: Record<string, unknown> | undefined
    server.use(
      http.post('/api/v1/finance/payments/payment-1/refund/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 'refund-1', status: 'approved' }, { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Acciones del pago VOUCHER-1' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Reembolsar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Reembolsar pago' })
    const amount = within(dialog).getByLabelText('Monto a devolver')
    await user.clear(amount)
    await user.type(amount, '50000')
    await user.type(within(dialog).getByLabelText('Motivo'), 'Descuento acordado')
    await user.type(within(dialog).getByLabelText('Texto de confirmación'), '50.000')
    await user.click(within(dialog).getByRole('button', { name: 'Reembolsar' }))

    await waitFor(() => expect(body).toEqual({ amount: '50000', reason: 'Descuento acordado', confirm: true }))
  })

  it('explains what happens to the money of each kind of payment before refunding', async () => {
    mockMe(makeMe())
    serveFolio(
      makeFolio({
        payments: [
          makePayment({
            id: 'payment-sim',
            method: 'wompi_card',
            provider: 'simulated',
            provider_reference: 'SIM-7Q2W',
            can_void: false,
          }),
          makePayment({ id: 'payment-pse', method: 'wompi_pse', provider: 'wompi', provider_reference: '1234-2-2', can_void: false }),
        ],
      }),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Acciones del pago SIM-7Q2W' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Reembolsar' }))
    let dialog = await screen.findByRole('dialog', { name: 'Reembolsar pago' })
    expect(within(dialog).getByText(/se aprueba al instante/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))

    await user.click(await screen.findByRole('button', { name: 'Acciones del pago 1234-2-2' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Reembolsar' }))
    dialog = await screen.findByRole('dialog', { name: 'Reembolsar pago' })
    expect(within(dialog).getByText(/Si Wompi no lo aprueba/)).toBeInTheDocument()
  })

  it('creates a payment link to copy or send', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    let body: Record<string, unknown> | undefined
    const intent = makeIntent({ amount: '483300.00' })
    server.use(
      http.post(`${DETAIL}payment-link/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ intent, checkout_url: intent.checkout_url, messages: [] }, { status: 201 })
      }),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Link de pago' }))
    const dialog = await screen.findByRole('dialog', { name: 'Link de pago' })
    await user.click(within(dialog).getByRole('checkbox', { name: /Enviar por email/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Crear link' }))

    expect(await within(dialog).findByDisplayValue(intent.checkout_url)).toBeInTheDocument()
    expect({ ...body, amount: Number(body!.amount) }).toEqual({ amount: 483300, send_via: ['email'] })
    expect(within(dialog).getByRole('button', { name: 'Copiar link' })).toBeInTheDocument()
  })

  it('shows only the actions the role allows', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['finance.view', 'finance.collect'], 'front_desk')] }))
    serveFolio(makeFolio())
    renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    expect(await screen.findByRole('button', { name: 'Registrar pago' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acciones de «Desayuno»' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acciones del pago VOUCHER-1' })).not.toBeInTheDocument()
  })

  it('keeps a closed folio read-only, refunds included', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio({ status: 'closed', closed_at: '2026-09-26T12:00:00-05:00' }))
    renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    expect(await screen.findByText('Folio cerrado')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar pago' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acciones de «Desayuno»' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acciones del pago VOUCHER-1' })).not.toBeInTheDocument()
  })

  it('says so when the hotel extras cannot be loaded', async () => {
    mockMe(makeMe())
    serveFolio(makeFolio())
    server.use(
      http.get(`${DETAIL}charge-options/`, () =>
        HttpResponse.json({ detail: 'Error interno', code: 'server_error' }, { status: 500 }),
      ),
    )
    const { user } = renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    await user.click(await screen.findByRole('button', { name: 'Agregar cargo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Agregar cargo' })

    expect(await within(dialog).findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(within(dialog).queryByText('El hotel no tiene extras activos')).not.toBeInTheDocument()
  })

  it('is read-only for people who can only look', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['finance.view'], 'custom')] }))
    serveFolio(makeFolio())
    renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    expect(await screen.findByText('$ 483.300')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar pago' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Agregar cargo' })).not.toBeInTheDocument()
  })

  it('opens the folio of a reservation that has none yet', async () => {
    mockMe(makeMe())
    let created = false
    let body: Record<string, unknown> | undefined
    server.use(
      http.get(LIST, () =>
        HttpResponse.json({ count: created ? 1 : 0, next: null, previous: null, results: created ? [summaryOf(makeFolio())] : [] }),
      ),
      http.post(LIST, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        created = true
        return HttpResponse.json(makeFolio(), { status: 201 })
      }),
      http.get(DETAIL, () => HttpResponse.json(makeFolio())),
    )
    renderWithProviders(<FolioPanel reservationId={RESERVATION_ID} />)

    expect(await screen.findByText('$ 483.300')).toBeInTheDocument()
    expect(body).toEqual({ reservation_id: RESERVATION_ID })
  })
})
