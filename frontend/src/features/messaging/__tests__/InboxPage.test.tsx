import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import InboxPage from '../pages/InboxPage'
import { CONVERSATION_ID, makeConversation, makeDetail, makeMessage, makeTemplates, page } from './fixtures'

const LIST = '/api/v1/messaging/conversations/'
const OTHER_ID = '0b9a4f5e-0000-4000-8000-00000000c002'

function serveInbox() {
  const queries: URLSearchParams[] = []
  const reads: string[] = []
  const email = makeConversation({
    id: OTHER_ID,
    channel: 'email',
    address: 'mateo@example.com',
    display_name: 'Mateo Ríos',
    contact_name: 'Mateo Ríos',
    guest: null,
    reservation: null,
    unread_count: 0,
    last_message_direction: 'out',
    last_message_preview: 'Te esperamos el viernes',
    whatsapp_window_open: null,
  })
  server.use(
    http.get(LIST, ({ request }) => {
      queries.push(new URL(request.url).searchParams)
      return HttpResponse.json(page([makeConversation(), email]))
    }),
    http.get(`${LIST}${CONVERSATION_ID}/`, () => HttpResponse.json(makeDetail())),
    http.get(`${LIST}${CONVERSATION_ID}/messages/`, () =>
      HttpResponse.json({
        results: [
          makeMessage({ id: 'm-1', direction: 'out', body: 'Tu reserva está confirmada ✅', status: 'read', sender_label: 'Hotel Casa Aurora', template_code: 'confirmation', created_at: '2026-09-20T14:00:00Z' }),
          makeMessage({ id: 'm-2', body: '¿Tienen toallas para la playa?' }),
          makeMessage({ id: 'm-3', direction: 'out', channel: 'internal_note', body: 'Pedí toallas a housekeeping', status: 'sent', sender_label: 'Andrés Gómez', created_at: '2026-09-25T15:30:00Z' }),
        ],
        has_more: false,
      }),
    ),
    http.post(`${LIST}${CONVERSATION_ID}/read/`, () => {
      reads.push(CONVERSATION_ID)
      return HttpResponse.json(makeConversation({ unread_count: 0 }))
    }),
    http.get('/api/v1/messaging/templates/', () => HttpResponse.json(makeTemplates())),
    http.get('/api/v1/messaging/conversations/unread-count/', () => HttpResponse.json({ conversations: 1, messages: 2 })),
    http.get('/api/v1/accounts/users/', () => HttpResponse.json(page([]))),
  )
  return { queries, reads }
}

beforeEach(() => {
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(makeMe())
})

describe('InboxPage', () => {
  it('lists the open conversations, newest first, with their channel, room and unread count', async () => {
    const { queries } = serveInbox()
    renderWithProviders(<InboxPage />, { route: '/app/inbox', path: '/app/inbox' })

    const list = await screen.findByRole('navigation', { name: 'Conversaciones' })
    const laura = await within(list).findByRole('link', { name: /Laura Gómez/ })
    expect(within(laura).getByText('¿Tienen toallas para la playa?')).toBeInTheDocument()
    expect(within(laura).getByText('WhatsApp')).toBeInTheDocument()
    expect(within(laura).getByText('301')).toBeInTheDocument()
    expect(within(laura).getByLabelText('2 mensajes sin leer')).toBeInTheDocument()
    const mateo = within(list).getByRole('link', { name: /Mateo Ríos/ })
    expect(within(mateo).getByText(/Tú:/)).toBeInTheDocument()
    expect(queries[0]?.get('status')).toBe('open')
    expect(screen.getByText('Elige una conversación')).toBeInTheDocument()
  })

  it('opens a conversation: thread with its note, booking beside it, and marks it read', async () => {
    const { reads } = serveInbox()
    const { user, router } = renderWithProviders(<InboxPage />, { route: '/app/inbox', path: '/app/inbox' })

    await user.click(await screen.findByRole('link', { name: /Laura Gómez/ }))

    expect(router.state.location.search).toBe(`?c=${CONVERSATION_ID}`)
    const thread = await screen.findByRole('list', { name: 'Mensajes con Laura Gómez' })
    expect(within(thread).getByText('Tu reserva está confirmada ✅')).toBeInTheDocument()
    expect(within(thread).getByText('Plantilla: Confirmación de reserva')).toBeInTheDocument()
    expect(within(thread).getByText('Pedí toallas a housekeeping')).toBeInTheDocument()
    expect(within(thread).getByText('Nota interna')).toBeInTheDocument()
    expect(screen.getByText(/ventana de WhatsApp/i)).toBeInTheDocument()
    const context = screen.getByRole('complementary', { name: 'Reserva y huésped' })
    expect(within(context).getByText('HT-LAURA1')).toBeInTheDocument()
    expect(within(context).getByText('$ 380.800')).toBeInTheDocument()
    await waitFor(() => expect(reads).toEqual([CONVERSATION_ID]))
    expect(screen.getByRole('form', { name: 'Responder a Laura Gómez' })).toBeInTheDocument()
  })

  it('filters by view, channel and search', async () => {
    const { queries } = serveInbox()
    const { user } = renderWithProviders(<InboxPage />, { route: '/app/inbox', path: '/app/inbox' })
    await screen.findByRole('link', { name: /Laura Gómez/ })

    await user.click(screen.getByRole('radio', { name: 'Sin leer' }))
    await waitFor(() => expect(queries.at(-1)?.get('unread')).toBe('1'))
    expect(queries.at(-1)?.get('status')).toBe('open')

    await user.click(screen.getByRole('radio', { name: 'Mías' }))
    await waitFor(() => expect(queries.at(-1)?.get('assigned')).toBe('me'))

    await user.click(screen.getByRole('radio', { name: 'Cerradas' }))
    await waitFor(() => expect(queries.at(-1)?.get('status')).toBe('closed'))

    await user.type(screen.getByRole('searchbox', { name: 'Buscar por nombre, reserva o teléfono' }), 'HT-LAURA1')
    await waitFor(() => expect(queries.at(-1)?.get('q')).toBe('HT-LAURA1'))
  })

  it('invites to try the simulator when nobody has written yet', async () => {
    server.use(
      http.get(LIST, () => HttpResponse.json(page([]))),
      http.get('/api/v1/messaging/conversations/unread-count/', () => HttpResponse.json({ conversations: 0, messages: 0 })),
    )
    renderWithProviders(<InboxPage />, { route: '/app/inbox', path: '/app/inbox' })

    expect(await screen.findByText('No hay conversaciones aquí')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Prueba el flujo con el simulador de WhatsApp.' })).toHaveAttribute(
      'href',
      '/app/simulators/whatsapp',
    )
  })
})
