import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import PublicWidget from '../public-widget'
import type { ChatCard, ChatConfig, ChatReply } from '../api'

const CHAT = '/api/v1/public/ai/chat/casa-aurora/'

function config(overrides: Partial<ChatConfig> = {}): ChatConfig {
  return {
    enabled: true,
    property: { name: 'Hotel Casa Aurora', slug: 'casa-aurora', city: 'Cartagena', primary_color: '#1F4E5A' },
    greeting: '¡Hola! Soy el asistente de Casa Aurora.',
    suggestions: ['¿Tienen parqueadero?'],
    languages: ['es', 'en'],
    session_id: null,
    messages: [],
    handoff: null,
    ...overrides,
  }
}

const offer: ChatCard = {
  type: 'offer',
  room_type_id: 'rt-1',
  room_type_code: 'DBL',
  room_type: 'Estándar',
  rate_plan: 'Tarifa flexible',
  total: '761600.00',
  per_night: '380800.00',
  currency: 'COP',
  available: 2,
  nights: 2,
  checkin: '2026-10-12',
  checkout: '2026-10-14',
  adults: 2,
  children: 0,
  url: '/h/casa-aurora?checkin=2026-10-12&checkout=2026-10-14&adults=2&children=0',
}

function reply(content: string, overrides: Partial<ChatReply> = {}): ChatReply {
  return {
    session_id: 'session-abcdefghijklmnop',
    reply: { role: 'assistant', content, cards: [], at: '2026-10-01T10:00:00-05:00' },
    handoff: { requested: false, contact_needed: false, contact_received: false },
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  document.cookie = 'csrftoken=t; path=/'
})

describe('PublicWidget', () => {
  it('renders nothing (and asks nothing) on pages without a hotel', () => {
    renderWithProviders(<PublicWidget />) // an unexpected request would fail the test (MSW: onUnhandledRequest error)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('stays hidden when the hotel switched its chatbot off', async () => {
    let asked = false
    server.use(
      http.get(CHAT, () => {
        asked = true
        return HttpResponse.json({ detail: 'Chat no disponible', code: 'not_found' }, { status: 404 })
      }),
    )

    renderWithProviders(<PublicWidget propertySlug="casa-aurora" />)

    await waitFor(() => expect(asked).toBe(true))
    expect(screen.queryByRole('button', { name: /Chatea con/ })).not.toBeInTheDocument()
  })

  it('answers availability with offer cards that open the booking engine', async () => {
    const sent: unknown[] = []
    server.use(
      http.get(CHAT, () => HttpResponse.json(config())),
      http.post(CHAT, async ({ request }) => {
        sent.push(await request.json())
        return HttpResponse.json(
          reply('Para el 12 → 14 de octubre hay disponibilidad.', {
            reply: { role: 'assistant', content: 'Para el 12 → 14 de octubre hay disponibilidad.', cards: [offer], at: null },
          }),
        )
      }),
    )
    const { user } = renderWithProviders(<PublicWidget propertySlug="casa-aurora" />)

    await user.click(await screen.findByRole('button', { name: 'Chatea con Hotel Casa Aurora' }))
    const chat = screen.getByRole('dialog', { name: 'Asistente de Hotel Casa Aurora' })
    expect(within(chat).getByText('¡Hola! Soy el asistente de Casa Aurora.')).toBeInTheDocument()
    await user.type(within(chat).getByRole('textbox', { name: 'Tu mensaje' }), '¿Tienen habitación del 12 al 14 de octubre?{Enter}')

    expect(await within(chat).findByText('Para el 12 → 14 de octubre hay disponibilidad.')).toBeInTheDocument()
    const card = within(chat).getByRole('article', { name: 'Estándar' })
    expect(within(card).getByText('$ 380.800 por noche')).toBeInTheDocument()
    expect(within(card).getByText('$ 761.600 por 2 noches')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Reservar/ })).toHaveAttribute('href', offer.url)
    expect(sent).toEqual([{ message: '¿Tienen habitación del 12 al 14 de octubre?', language: 'es' }])
    expect(localStorage.getItem('housetel.chat.casa-aurora')).toBe('session-abcdefghijklmnop')
  })

  it('asks for a way to reach the guest when it hands the chat to a person', async () => {
    const contacts: unknown[] = []
    server.use(
      http.get(CHAT, () => HttpResponse.json(config())),
      http.post(CHAT, () =>
        HttpResponse.json(
          reply('Con gusto te comunico con el equipo del hotel.', {
            handoff: { requested: true, contact_needed: true, contact_received: false },
          }),
        ),
      ),
      http.post(`${CHAT}contact/`, async ({ request }) => {
        contacts.push(await request.json())
        return HttpResponse.json({ ok: true, handoff: { requested: true, contact_needed: false, contact_received: true } })
      }),
    )
    const { user } = renderWithProviders(<PublicWidget propertySlug="casa-aurora" />)

    await user.click(await screen.findByRole('button', { name: 'Chatea con Hotel Casa Aurora' }))
    const chat = screen.getByRole('dialog', { name: 'Asistente de Hotel Casa Aurora' })
    await user.type(within(chat).getByRole('textbox', { name: 'Tu mensaje' }), 'Quiero hablar con una persona{Enter}')

    const form = await within(chat).findByRole('form', { name: 'Déjanos tus datos' })
    await user.click(within(form).getByRole('button', { name: 'Enviar mis datos' }))
    expect(await within(form).findByText('Déjanos un correo o un teléfono.')).toBeInTheDocument()
    expect(contacts).toEqual([])

    await user.type(within(form).getByLabelText('Nombre'), 'Marta Ruiz')
    await user.type(within(form).getByLabelText('Correo'), 'marta@example.com')
    await user.click(within(form).getByRole('button', { name: 'Enviar mis datos' }))

    expect(await within(chat).findByText('Listo: recibimos tus datos y el equipo te contactará pronto.')).toBeInTheDocument()
    expect(contacts).toEqual([
      { session_id: 'session-abcdefghijklmnop', name: 'Marta Ruiz', email: 'marta@example.com', phone: '', message: '' },
    ])
  })

  it('picks up the conversation the guest already had on this hotel', async () => {
    localStorage.setItem('housetel.chat.casa-aurora', 'session-abcdefghijklmnop')
    const sessions: (string | null)[] = []
    server.use(
      http.get(CHAT, ({ request }) => {
        sessions.push(new URL(request.url).searchParams.get('session_id'))
        return HttpResponse.json(
          config({
            session_id: 'session-abcdefghijklmnop',
            messages: [
              { role: 'user', content: '¿Aceptan mascotas?', cards: [], at: null },
              { role: 'assistant', content: 'No aceptamos mascotas.', cards: [], at: null },
            ],
          }),
        )
      }),
    )
    const { user } = renderWithProviders(<PublicWidget propertySlug="casa-aurora" />)

    await user.click(await screen.findByRole('button', { name: 'Chatea con Hotel Casa Aurora' }))

    expect(screen.getByText('No aceptamos mascotas.')).toBeInTheDocument()
    expect(sessions).toEqual(['session-abcdefghijklmnop'])
  })

  it('talks to the guest portal chat when mounted on the portal', async () => {
    const TOKEN_CHAT = '/api/v1/public/ai/portal-chat/token-123/'
    server.use(http.get(TOKEN_CHAT, () => HttpResponse.json(config())))

    renderWithProviders(<PublicWidget portalToken="token-123" />)

    expect(await screen.findByRole('button', { name: 'Chatea con Hotel Casa Aurora' })).toBeInTheDocument()
  })
})
