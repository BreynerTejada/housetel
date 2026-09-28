import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { PortalSummary } from '../api'
import { goTo } from '../lib/navigation'
import PortalPage from '../pages/PortalPage'
import { makeSummary, TOKEN } from './fixtures'

vi.mock('../lib/navigation', () => ({ goTo: vi.fn() }))

const BASE = `/api/v1/public/guestportal/${encodeURIComponent(TOKEN)}/`
const INVOICES = `/api/v1/public/compliance/portal/${encodeURIComponent(TOKEN)}/invoices/`

function serve(summary: PortalSummary, { invoices }: { invoices?: unknown[] } = {}) {
  const posts: { url: string; body: unknown }[] = []
  let current = summary
  server.use(
    http.get(BASE, () => HttpResponse.json(current)),
    http.get(INVOICES, () => (invoices ? HttpResponse.json(invoices) : new HttpResponse('<h1>Not Found</h1>', { status: 404 }))),
    http.post(`${BASE}pay/`, async ({ request }) => {
      posts.push({ url: 'pay/', body: await request.json() })
      return HttpResponse.json({ reference: 'HT-7K2M9Q-AB12CD', checkout_url: 'http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD' }, { status: 201 })
    }),
    http.post(`${BASE}requests/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      posts.push({ url: 'requests/', body })
      const created = {
        id: `req-${posts.length}`,
        kind: body.kind,
        status: body.kind === 'extra' ? 'approved' : 'requested',
        extra: body.kind === 'extra' ? { id: 'extra-brk', code: 'BRK', name: { es: 'Desayuno', en: 'Breakfast' } } : null,
        quantity: body.quantity ?? 1,
        requested_time: body.requested_time ?? null,
        notes: body.notes ?? '',
        price: body.kind === 'extra' ? '166600.00' : null,
        decision_note: '',
        created_at: '2026-10-01T10:00:00-05:00',
        decided_at: null,
      }
      current = { ...current, requests: [created as PortalSummary['requests'][number], ...current.requests] }
      return HttpResponse.json({ request: created, ...current }, { status: 201 })
    }),
    http.post(`${BASE}cancel/`, async ({ request }) => {
      posts.push({ url: 'cancel/', body: await request.json() })
      current = { ...current, reservation: { ...current.reservation, status: 'cancelled', cancelled_at: '2026-10-01T10:00:00-05:00' } }
      return HttpResponse.json(current)
    }),
  )
  return posts
}

function renderPage(search = '') {
  return renderWithProviders(<PortalPage />, { route: `/g/${encodeURIComponent(TOKEN)}${search}`, path: '/g/:token' })
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  vi.mocked(goTo).mockReset()
  localStorage.setItem('housetel.portal.lang:HT-7K2M9Q', '1')
})

describe('PortalPage', () => {
  it('shows the booking as a registration card with the online check-in to do', async () => {
    serve(makeSummary())
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Hola, Laura' })).toBeInTheDocument()
    expect(screen.getByText('Tu estadía en Cartagena empieza en 4 días.')).toBeInTheDocument()
    const card = screen.getByRole('article', { name: 'HT-7K2M9Q' })
    expect(within(card).getByText('2 noches · 2 adultos')).toBeInTheDocument()
    expect(within(card).getByText(/Estándar · Tarifa flexible/)).toBeInTheDocument()
    const checkin = within(card).getByRole('link', { name: 'Hacer check-in' })
    expect(checkin).toHaveAttribute('href', `/g/${encodeURIComponent(TOKEN)}/checkin`)
    expect(screen.queryByRole('heading', { name: 'Facturas' })).not.toBeInTheDocument() // C7 not there yet → hidden
  })

  it('shows a completed check-in as ready for arrival', async () => {
    serve(
      makeSummary({
        checkin: { status: 'completed', current_step: 'done', completed_at: '2026-10-01T09:00:00-05:00', opens_on: '2026-09-28', is_open: true, reason: null },
        reservation: { ...makeSummary().reservation, eta: '16:30' },
      }),
    )
    renderPage()

    const card = await screen.findByRole('article', { name: 'HT-7K2M9Q' })
    expect(within(card).getByText('Check-in listo')).toBeInTheDocument()
    expect(within(card).getByText('Te esperamos. Llegada estimada: 16:30.')).toBeInTheDocument()
  })

  it('takes the guest to the gateway to pay the balance', async () => {
    const posts = serve(makeSummary())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Pagar $ 761.600' }))
    const dialog = await screen.findByRole('dialog', { name: 'Pagar tu saldo' })
    await user.click(within(dialog).getByRole('button', { name: 'Pagar $ 761.600' }))

    await waitFor(() => expect(goTo).toHaveBeenCalledWith('http://localhost:5173/sim/pay/HT-7K2M9Q-AB12CD'))
    expect(posts).toEqual([{ url: 'pay/', body: {} }])
  })

  it('confirms the payment when the guest comes back from the gateway', async () => {
    serve(makeSummary())
    server.use(
      http.get('/api/v1/public/finance/intents/HT-7K2M9Q-AB12CD/status/', () =>
        HttpResponse.json({ reference: 'HT-7K2M9Q-AB12CD', status: 'approved', paid: true, amount: '761600.00', currency: 'COP', method: 'wompi_card', reservation_code: 'HT-7K2M9Q', property_slug: 'casa-aurora' }),
      ),
    )
    renderPage('?paid=1&payment_ref=HT-7K2M9Q-AB12CD')

    expect(await screen.findByText('Recibimos tu pago. ¡Gracias!')).toBeInTheDocument()
  })

  it('adds an extra to the account', async () => {
    const posts = serve(makeSummary())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Agregar Desayuno' }))
    const dialog = await screen.findByRole('dialog', { name: 'Agregar Desayuno' })
    expect(within(dialog).getByLabelText('Cantidad')).toHaveValue(4)
    expect(within(dialog).getByText('$ 166.600')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Agregar a mi cuenta' }))

    expect(await screen.findByText('Desayuno quedó en tu cuenta.')).toBeInTheDocument()
    expect(posts).toEqual([{ url: 'requests/', body: { kind: 'extra', extra_id: 'extra-brk', quantity: 4 } }])
    expect(within(screen.getByRole('region', { name: '¿Necesitas algo?' })).getByText('Desayuno × 4')).toBeInTheDocument()
  })

  it('asks the hotel for a late check-out', async () => {
    const posts = serve(makeSummary())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Salir más tarde' }))
    const dialog = await screen.findByRole('dialog', { name: 'Salir más tarde' })
    await user.type(within(dialog).getByLabelText('Detalles (opcional)'), 'Vuelo a las 6 pm')
    await user.click(within(dialog).getByRole('button', { name: 'Enviar solicitud' }))

    expect(await screen.findByText('Solicitud enviada. El hotel te responderá pronto.')).toBeInTheDocument()
    expect(posts).toEqual([{ url: 'requests/', body: { kind: 'late_checkout', requested_time: '14:00', notes: 'Vuelo a las 6 pm' } }])
  })

  it('needs the details of a transfer before sending it', async () => {
    const posts = serve(makeSummary())
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Traslado' }))
    const dialog = await screen.findByRole('dialog', { name: 'Traslado' })
    await user.click(within(dialog).getByRole('button', { name: 'Enviar solicitud' }))

    expect(within(dialog).getByLabelText('Detalles')).toHaveAccessibleDescription('Este campo es obligatorio')
    expect(posts).toEqual([])
  })

  it('cancels for free inside the free window', async () => {
    const posts = serve(makeSummary())
    const { user } = renderPage()

    expect(await screen.findByText('Cancelación gratuita hasta el 3 de octubre a las 15:00 (hora del hotel).')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancelar reserva' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cancelar la reserva HT-7K2M9Q?' })
    expect(within(dialog).getByText('Cancelar ahora no tiene costo.')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar reserva' }))

    expect(await screen.findByText('Esta reserva está cancelada.')).toBeInTheDocument()
    expect(posts).toEqual([{ url: 'cancel/', body: { confirm: true, reason: '' } }])
  })

  it('makes the guest acknowledge the penalty before cancelling with a fee', async () => {
    serve(makeSummary({ cancellation: { ...makeSummary().cancellation, fee: '380800.00', fee_reason: 'first_night' } }))
    const { user } = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Cancelar reserva' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cancelar la reserva HT-7K2M9Q?' })
    const confirm = within(dialog).getByRole('button', { name: 'Cancelar reserva' })
    expect(confirm).toBeDisabled()

    await user.click(within(dialog).getByRole('checkbox', { name: 'Entiendo que se cobrarán $ 380.800.' }))
    expect(confirm).toBeEnabled()
  })

  it('explains why a channel booking is changed on the channel', async () => {
    serve(
      makeSummary({
        cancellation: { ...makeSummary().cancellation, can_cancel: false, reason: 'channel' },
        modification: { ...makeSummary().modification, can_modify: false, reason: 'channel' },
      }),
    )
    renderPage()

    expect(await screen.findByText('Reservaste por un canal externo: cancela desde allí.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar reserva' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cambiar fechas' })).not.toBeInTheDocument()
  })

  it('lists the invoices once the hotel issues them', async () => {
    serve(makeSummary(), {
      invoices: [{ id: 'inv-1', number: 'SETT-120', kind: 'invoice', status: 'accepted', total: '761600.00', issued_at: '2026-10-07T12:30:00-05:00', pdf_url: '/api/v1/public/compliance/portal/x/invoices/inv-1/pdf/' }],
    })
    renderPage()

    const invoices = await screen.findByRole('region', { name: 'Facturas' })
    expect(within(invoices).getByText('Factura electrónica SETT-120')).toBeInTheDocument()
    expect(within(invoices).getByRole('link', { name: 'Descargar PDF' })).toHaveAttribute('href', '/api/v1/public/compliance/portal/x/invoices/inv-1/pdf/')
  })

  it('explains that an altered link does not open any booking', async () => {
    server.use(http.get(BASE, () => HttpResponse.json({ detail: 'x', code: 'invalid_link' }, { status: 404 })))
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Este enlace no es válido' })).toBeInTheDocument()
  })
})
