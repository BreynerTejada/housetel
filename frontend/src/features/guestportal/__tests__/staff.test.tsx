import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import type { ArrivalCheckin, StaffServiceRequest } from '../api'
import { CheckinTab, RequestsTab } from '../components/staff/ReservationTabs'
import { LinkQrAction, SendLinkAction } from '../components/staff/LinkActions'
import { OnlineCheckinWidget } from '../components/staff/OnlineCheckinWidget'
import { reservationActions } from '../reservation-actions'
import { reservationTabs } from '../reservation-tabs'
import { widgets } from '../widgets'
import { makeStaffCheckin, TOKEN } from './fixtures'

const RES = 'res-1'
const CHECKIN_URL = `/api/v1/guestportal/reservations/${RES}/checkin/`

function lateCheckout(overrides: Partial<StaffServiceRequest> = {}): StaffServiceRequest {
  return {
    id: 'req-1',
    kind: 'late_checkout',
    status: 'requested',
    extra: null,
    quantity: 1,
    requested_time: '14:00',
    notes: 'Vuelo a las 6 pm',
    price: null,
    decision_note: '',
    created_at: '2026-10-01T09:00:00-05:00',
    decided_at: null,
    reservation: { id: RES, code: 'HT-7K2M9Q', guest_name: 'Laura Gómez', checkin_date: '2026-10-05', checkout_date: '2026-10-07', status: 'confirmed' },
    ...overrides,
  }
}

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  mockMe(makeMe())
  URL.createObjectURL = vi.fn(() => 'blob:private')
  URL.revokeObjectURL = vi.fn()
})

describe('extension points', () => {
  it('registers the reservation tabs, the actions and the Today widget with their permissions', () => {
    expect(reservationTabs.map((tab) => [tab.id, tab.permission])).toEqual([
      ['guestportal-checkin', 'guestportal.view'],
      ['guestportal-requests', 'guestportal.view'],
    ])
    expect(reservationActions.map((action) => [action.id, action.permission])).toEqual([
      ['guestportal-send-link', 'guestportal.manage'],
      ['guestportal-link', 'guestportal.view'],
    ])
    expect(widgets.map((widget) => [widget.id, widget.permission])).toEqual([['guestportal-checkins', 'guestportal.view']])
  })
})

describe('CheckinTab', () => {
  it('shows what the guest registered online, the ID photo and the signature', async () => {
    const files: string[] = []
    server.use(
      http.get(CHECKIN_URL, () => HttpResponse.json(makeStaffCheckin())),
      http.get('/api/v1/guests/documents/doc-1/file/', ({ request }) => {
        files.push(new URL(request.url).pathname)
        return new HttpResponse(new Blob(['jpg'], { type: 'image/jpeg' }), { headers: { 'Content-Type': 'image/jpeg' } })
      }),
      http.get(`/api/v1/guestportal/reservations/${RES}/checkin/signature/`, ({ request }) => {
        files.push(new URL(request.url).pathname)
        return new HttpResponse(new Blob(['png'], { type: 'image/png' }), { headers: { 'Content-Type': 'image/png' } })
      }),
    )
    renderWithProviders(<CheckinTab reservationId={RES} />)

    expect(await screen.findByText('Completado')).toBeInTheDocument()
    const laura = screen.getByRole('region', { name: 'Laura Gómez' })
    expect(within(laura).getByText('CC 52123456')).toBeInTheDocument()
    expect(within(laura).getByText('Trabajo o negocios · de Bogotá a Cartagena')).toBeInTheDocument()
    expect(await within(laura).findByRole('img', { name: 'Documento (frente) de Laura Gómez' })).toHaveAttribute('src', 'blob:private')
    expect(await screen.findByRole('img', { name: 'Firma de Laura Gómez' })).toHaveAttribute('src', 'blob:private')
    expect(screen.getByText(/desde 181\.52\.10\.4/)).toBeInTheDocument()
    expect(files.sort()).toEqual([`/api/v1/guestportal/reservations/${RES}/checkin/signature/`, '/api/v1/guests/documents/doc-1/file/'])
    expect(document.body.innerHTML).not.toContain('/media/')
  })

  it('invites to send the link when the guest has not started', async () => {
    server.use(
      http.get(CHECKIN_URL, () =>
        HttpResponse.json(
          makeStaffCheckin({
            status: 'not_started',
            current_step: 'guests',
            completed_at: null,
            accepted_terms_at: null,
            eta: null,
            ip: null,
            user_agent: '',
            signature_url: null,
            guests: [{ ...makeStaffCheckin().guests[0]!, complete: false, documents: [] }],
            missing: [{ code: 'guest_data', slot: 0 }, { code: 'document', guest_id: 'guest-booker' }, { code: 'signature' }],
          }),
        ),
      ),
    )
    renderWithProviders(<CheckinTab reservationId={RES} />)

    expect(await screen.findByText('El huésped aún no hace el check-in online')).toBeInTheDocument()
    const missing = screen.getByRole('list', { name: 'Falta para completarlo' })
    expect(within(missing).getByText('Foto del documento de Laura Gómez')).toBeInTheDocument()
    expect(within(missing).getByText('Firma')).toBeInTheDocument()
  })
})

describe('RequestsTab', () => {
  function serveRequests(list: StaffServiceRequest[]) {
    const posts: { url: string; body: unknown }[] = []
    server.use(
      http.get('/api/v1/guestportal/service-requests/', () => HttpResponse.json({ count: list.length, next: null, previous: null, results: list })),
      http.get('/api/v1/rates/extras/', () =>
        HttpResponse.json({ count: 1, next: null, previous: null, results: [{ id: 'extra-late', code: 'LATE', name: { es: 'Late check-out', en: 'Late check-out' }, price: '80000.00', charge_type: 'per_stay', is_active: true }] }),
      ),
      http.post('/api/v1/guestportal/service-requests/req-1/approve/', async ({ request }) => {
        posts.push({ url: 'approve', body: await request.json() })
        return HttpResponse.json(lateCheckout({ status: 'approved', price: '95200.00' }))
      }),
      http.post('/api/v1/guestportal/service-requests/req-1/reject/', async ({ request }) => {
        posts.push({ url: 'reject', body: await request.json() })
        return HttpResponse.json(lateCheckout({ status: 'rejected', decision_note: 'Hotel lleno' }))
      }),
    )
    return posts
  }

  it('approves a late check-out charging the catalog extra', async () => {
    const posts = serveRequests([lateCheckout()])
    const { user } = renderWithProviders(<RequestsTab reservationId={RES} />)

    const row = await screen.findByRole('listitem', { name: /Late check-out/ })
    expect(within(row).getByText('hasta las 14:00')).toBeInTheDocument()
    expect(within(row).getByText('Vuelo a las 6 pm')).toBeInTheDocument()
    await user.click(await within(row).findByRole('button', { name: 'Aprobar' })) // permissions come with `me`
    const dialog = await screen.findByRole('dialog', { name: 'Aprobar: Late check-out' })
    await user.click(within(dialog).getByRole('combobox', { name: 'Cobrar' }))
    await user.click(await screen.findByRole('option', { name: /Late check-out/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Aprobar' }))

    expect(await screen.findByText('Solicitud aprobada')).toBeInTheDocument()
    expect(posts).toEqual([{ url: 'approve', body: { extra_id: 'extra-late', quantity: 1, note: '' } }])
  })

  it('declines with a reason the guest will see', async () => {
    const posts = serveRequests([lateCheckout()])
    const { user } = renderWithProviders(<RequestsTab reservationId={RES} />)

    await user.click(await within(await screen.findByRole('listitem', { name: /Late check-out/ })).findByRole('button', { name: 'Rechazar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Rechazar: Late check-out' })
    await user.type(within(dialog).getByLabelText('Motivo que verá el huésped (opcional)'), 'Hotel lleno')
    await user.click(within(dialog).getByRole('button', { name: 'Rechazar' }))

    expect(await screen.findByText('Solicitud rechazada')).toBeInTheDocument()
    expect(posts).toEqual([{ url: 'reject', body: { reason: 'Hotel lleno' } }])
  })

  it('only shows the decisions to whoever manages the portal', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['guestportal.view'], 'custom')] }))
    serveRequests([lateCheckout()])
    renderWithProviders(<RequestsTab reservationId={RES} />)

    const row = await screen.findByRole('listitem', { name: /Late check-out/ })
    await waitFor(() => expect(within(row).queryByRole('button', { name: 'Aprobar' })).not.toBeInTheDocument())
  })
})

describe('link actions', () => {
  it('sends the check-in invitation and says through which channel', async () => {
    const posts: unknown[] = []
    server.use(
      http.get(CHECKIN_URL, () => HttpResponse.json(makeStaffCheckin())),
      http.post(`/api/v1/guestportal/reservations/${RES}/send-link/`, async ({ request }) => {
        posts.push(await request.json())
        return HttpResponse.json({ url: 'u', checkin_url: 'u/checkin', messages: [{ channel: 'email', to: 'laura@example.com', status: 'sent', error: '' }] })
      }),
    )
    const close = vi.fn()
    const { user } = renderWithProviders(<SendLinkAction reservationId={RES} close={close} />)

    const dialog = await screen.findByRole('dialog', { name: 'Enviar link de check-in' })
    expect(await within(dialog).findByText(/Laura Gómez/)).toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: /Correo/ })).toBeChecked()
    await user.click(within(dialog).getByRole('button', { name: 'Enviar link' }))

    expect(await within(dialog).findByText('Link enviado por Correo.')).toBeInTheDocument()
    expect(posts).toEqual([{ send_via: ['email'] }])
  })

  it('offers the link to copy when nothing could be sent', async () => {
    server.use(
      http.get(CHECKIN_URL, () => HttpResponse.json(makeStaffCheckin())),
      http.post(`/api/v1/guestportal/reservations/${RES}/send-link/`, () =>
        HttpResponse.json({ url: `http://localhost:5173/g/${TOKEN}`, checkin_url: `http://localhost:5173/g/${TOKEN}/checkin`, messages: [] }),
      ),
    )
    const { user } = renderWithProviders(<SendLinkAction reservationId={RES} close={vi.fn()} />)

    const dialog = await screen.findByRole('dialog', { name: 'Enviar link de check-in' })
    await user.click(await within(dialog).findByRole('button', { name: 'Enviar link' }))

    expect(await within(dialog).findByText('No se envió ningún mensaje. Copia el link y compártelo tú.')).toBeInTheDocument()
    expect(within(dialog).getByDisplayValue(`http://localhost:5173/g/${TOKEN}/checkin`)).toBeInTheDocument()
  })

  it('shows the portal link with its QR code and copies it', async () => {
    server.use(
      http.get(`/api/v1/guestportal/reservations/${RES}/link/`, () =>
        HttpResponse.json({ url: `http://localhost:5173/g/${TOKEN}`, checkin_url: `http://localhost:5173/g/${TOKEN}/checkin`, qr_png: 'data:image/png;base64,QR' }),
      ),
    )
    const { user } = renderWithProviders(<LinkQrAction reservationId={RES} close={vi.fn()} />)

    const dialog = await screen.findByRole('dialog', { name: 'Link del portal del huésped' })
    expect(await within(dialog).findByRole('img', { name: 'Código QR del portal' })).toHaveAttribute('src', 'data:image/png;base64,QR')
    await user.click(within(dialog).getAllByRole('button', { name: 'Copiar' })[0]!)

    expect(await navigator.clipboard.readText()).toBe(`http://localhost:5173/g/${TOKEN}`)
    expect(within(dialog).getByRole('link', { name: 'Abrir portal' })).toHaveAttribute('href', `http://localhost:5173/g/${TOKEN}`)
  })
})

describe('OnlineCheckinWidget', () => {
  it('counts the arrivals ready and lists who is missing', async () => {
    const arrivals: ArrivalCheckin[] = [
      { reservation_id: 'r1', code: 'HT-AAA111', status: 'confirmed', guest_name: 'Laura Gómez', is_vip: true, adults: 2, children: 0, checkin_status: 'completed', completed_at: '2026-10-01T08:00:00-05:00', eta: '16:30' },
      { reservation_id: 'r2', code: 'HT-BBB222', status: 'confirmed', guest_name: 'John Smith', is_vip: false, adults: 1, children: 0, checkin_status: 'not_started', completed_at: null, eta: null },
    ]
    server.use(
      http.get('/api/v1/guestportal/checkins/', () => HttpResponse.json(arrivals)),
      http.get('/api/v1/guestportal/service-requests/', () => HttpResponse.json({ count: 1, next: null, previous: null, results: [lateCheckout()] })),
    )
    renderWithProviders(<OnlineCheckinWidget />)

    const widget = await screen.findByRole('region', { name: 'Check-in online de hoy' })
    expect(await within(widget).findByText('1 de 2 llegadas listas')).toBeInTheDocument()
    expect(within(widget).getByRole('link', { name: /Laura Gómez/ })).toHaveAttribute('href', '/app/reservations/r1')
    expect(within(widget).getByText('Sin empezar')).toBeInTheDocument()
    expect(await within(widget).findByText('1 solicitud por atender')).toBeInTheDocument()
  })
})
