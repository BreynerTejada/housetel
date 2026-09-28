import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import WhatsAppSimulatorPage from '../pages/WhatsAppSimulatorPage'
import { CONVERSATION_ID, GUEST_ID, makeMessage, RESERVATION_ID } from './fixtures'

const BASE = '/api/v1/messaging/simulator/whatsapp/'
const LAURA = {
  guest_id: GUEST_ID,
  full_name: 'Laura Gómez',
  phone: '+573001112233',
  reservation: { id: RESERVATION_ID, code: 'HT-LAURA1', status: 'confirmed', checkin_date: '2026-09-26', checkout_date: '2026-09-28' },
}

function serveSimulator({ enabled = true } = {}) {
  const inbound: Record<string, unknown>[] = []
  const threads: string[] = []
  let replied = false
  server.use(
    http.get(`${BASE}contacts/`, () => HttpResponse.json({ simulator_enabled: enabled, results: [LAURA] })),
    http.get(`${BASE}thread/`, ({ request }) => {
      const phone = new URL(request.url).searchParams.get('phone') ?? ''
      threads.push(phone)
      const messages = replied
        ? [
            makeMessage({ id: 'in-1', body: 'Hola, ¿a qué hora es el check-in?' }),
            makeMessage({ id: 'out-1', direction: 'out', body: '¡Hola Laura! Desde las 3 p. m.', status: 'delivered', sender_label: 'Andrés Gómez', created_at: '2026-09-25T15:21:00Z' }),
          ]
        : []
      return HttpResponse.json({
        phone: phone.startsWith('+') ? phone : `+57${phone}`,
        simulator_enabled: enabled,
        conversation_id: replied ? CONVERSATION_ID : null,
        guest: phone.includes('3001112233') ? { id: GUEST_ID, full_name: 'Laura Gómez', language: 'es' } : null,
        messages,
      })
    }),
    http.post(`${BASE}inbound/`, async ({ request }) => {
      inbound.push((await request.json()) as Record<string, unknown>)
      replied = true
      return HttpResponse.json(
        { message: makeMessage({ id: 'in-1', body: 'Hola, ¿a qué hora es el check-in?' }), conversation_id: CONVERSATION_ID },
        { status: 201 },
      )
    }),
  )
  return { inbound, threads }
}

beforeEach(() => {
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(makeMe())
})

describe('WhatsAppSimulatorPage', () => {
  it('plays an arriving guest: writes as them and sees the hotel’s reply on the phone', async () => {
    const { inbound, threads } = serveSimulator()
    const { user } = renderWithProviders(<WhatsAppSimulatorPage />)

    await user.click(await screen.findByRole('button', { name: /Laura Gómez/ }))
    const phone = await screen.findByRole('region', { name: 'Teléfono de Laura Gómez' })
    expect(await within(phone).findByText('Aún no hay mensajes. Saluda al hotel.')).toBeInTheDocument()

    await user.type(within(phone).getByRole('textbox', { name: 'Mensaje' }), 'Hola, ¿a qué hora es el check-in?')
    await user.click(within(phone).getByRole('button', { name: 'Enviar como huésped' }))

    await waitFor(() => expect(inbound).toHaveLength(1))
    expect(inbound[0]).toEqual({ phone: '+573001112233', body: 'Hola, ¿a qué hora es el check-in?', name: '' })
    expect(await within(phone).findByText('¡Hola Laura! Desde las 3 p. m.')).toBeInTheDocument()
    expect(within(phone).getByText('Hola, ¿a qué hora es el check-in?')).toBeInTheDocument()
    expect(threads.every((value) => value === '+573001112233')).toBe(true)
    expect(screen.getByRole('link', { name: 'Ver en la bandeja' })).toHaveAttribute('href', `/app/inbox?c=${CONVERSATION_ID}`)
  })

  it('writes from a new number with its WhatsApp name', async () => {
    const { inbound } = serveSimulator()
    const { user } = renderWithProviders(<WhatsAppSimulatorPage />)

    await user.type(await screen.findByRole('textbox', { name: 'Teléfono del huésped' }), '+14155550100')
    await user.type(screen.getByRole('textbox', { name: 'Nombre en WhatsApp' }), 'Sheena Nelson')
    await user.click(screen.getByRole('button', { name: 'Usar este número' }))

    const phone = await screen.findByRole('region', { name: 'Teléfono de Sheena Nelson' })
    expect(within(phone).getByText('Número nuevo: al escribir se crea como contacto')).toBeInTheDocument()
    await user.type(within(phone).getByRole('textbox', { name: 'Mensaje' }), 'Hi!')
    await user.click(within(phone).getByRole('button', { name: 'Enviar como huésped' }))

    await waitFor(() => expect(inbound).toHaveLength(1))
    expect(inbound[0]).toEqual({ phone: '+14155550100', body: 'Hi!', name: 'Sheena Nelson' })
  })

  it('is off while the hotel sends real WhatsApp messages', async () => {
    serveSimulator({ enabled: false })
    const { user } = renderWithProviders(<WhatsAppSimulatorPage />)

    expect(await screen.findByText('El simulador está apagado')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir a integraciones' })).toHaveAttribute('href', '/app/settings/integrations')
    await user.type(screen.getByRole('textbox', { name: 'Teléfono del huésped' }), '+573001112233')
    expect(screen.getByRole('button', { name: 'Usar este número' })).toBeDisabled()
  })
})
