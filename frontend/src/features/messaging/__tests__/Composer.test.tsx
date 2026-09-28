import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { Composer } from '../components/Composer'
import { CONVERSATION_ID, makeConversation, makeMessage, makeTemplates } from './fixtures'

const MESSAGES = `/api/v1/messaging/conversations/${CONVERSATION_ID}/messages/`

function captureReply() {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.post(MESSAGES, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      bodies.push(body)
      return HttpResponse.json(
        makeMessage({
          id: 'm-out',
          direction: 'out',
          channel: body.internal ? 'internal_note' : 'whatsapp',
          body: String(body.body),
          status: body.internal ? 'sent' : 'delivered',
        }),
        { status: 201 },
      )
    }),
  )
  return bodies
}

beforeEach(() => {
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(makeMe())
  server.use(http.get('/api/v1/messaging/templates/', () => HttpResponse.json(makeTemplates())))
})

describe('Composer', () => {
  it('inserts a template filled with the guest’s data and sends it with its code', async () => {
    const previews: Record<string, unknown>[] = []
    server.use(
      http.post('/api/v1/messaging/templates/preview/', async ({ request }) => {
        previews.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({
          channel: 'whatsapp', language: 'es', source: 'system', sample: false, subject: '',
          text: 'Hola Laura, tu reserva HT-LAURA1 está confirmada.',
          whatsapp: 'Hola Laura, tu reserva HT-LAURA1 está confirmada.',
          markup: 'Hola Laura, tu reserva **HT-LAURA1** está confirmada.',
          html: '', missing: [], unknown: [],
        })
      }),
    )
    const replies = captureReply()
    const { user } = renderWithProviders(<Composer conversation={makeConversation()} />)

    await user.click(await screen.findByRole('button', { name: 'Plantilla' }))
    await user.click(await screen.findByRole('button', { name: 'Confirmación de reserva' }))

    const box = screen.getByRole('textbox', { name: 'Responder' })
    await waitFor(() => expect(box).toHaveValue('Hola Laura, tu reserva **HT-LAURA1** está confirmada.'))
    expect(previews).toEqual([{ channel: 'whatsapp', template_code: 'confirmation', conversation_id: CONVERSATION_ID }])
    // Only the WhatsApp templates of the conversation's channel are offered (custom ones included).
    await user.click(screen.getByRole('button', { name: 'Plantilla' }))
    expect(await screen.findByRole('button', { name: 'Cóctel de bienvenida' })).toBeInTheDocument()
    await user.keyboard('{Escape}')

    await user.click(screen.getByRole('button', { name: 'Enviar por WhatsApp' }))

    await waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toEqual({
      body: 'Hola Laura, tu reserva **HT-LAURA1** está confirmada.',
      subject: '',
      internal: false,
      template_code: 'confirmation',
      ai_generated: false,
    })
    await waitFor(() => expect(box).toHaveValue(''))
  })

  it('saves an internal note that the guest never receives', async () => {
    const replies = captureReply()
    const { user } = renderWithProviders(<Composer conversation={makeConversation()} />)

    await user.click(await screen.findByRole('radio', { name: 'Nota interna' }))
    await user.type(screen.getByRole('textbox', { name: 'Nota interna' }), 'Pedir toallas a housekeeping')
    await user.click(screen.getByRole('button', { name: 'Guardar nota' }))

    await waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toMatchObject({ body: 'Pedir toallas a housekeeping', internal: true, template_code: '' })
  })

  it('sends with Ctrl + Enter and refuses an empty message', async () => {
    const replies = captureReply()
    const { user } = renderWithProviders(<Composer conversation={makeConversation()} />)

    const box = await screen.findByRole('textbox', { name: 'Responder' })
    await user.click(box)
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe un mensaje antes de enviar.')
    expect(replies).toHaveLength(0)

    await user.type(box, 'Sí, en recepción')
    await user.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toMatchObject({ body: 'Sí, en recepción', internal: false })
  })

  it('writes the email subject', async () => {
    const replies = captureReply()
    const { user } = renderWithProviders(
      <Composer conversation={makeConversation({ channel: 'email', address: 'laura@example.com' })} />,
    )

    await user.type(await screen.findByRole('textbox', { name: 'Asunto' }), 'Tu cama adicional')
    await user.type(screen.getByRole('textbox', { name: 'Responder' }), 'Listo, sin costo.')
    await user.click(screen.getByRole('button', { name: 'Enviar por Correo' }))

    await waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toMatchObject({ subject: 'Tu cama adicional', body: 'Listo, sin costo.' })
  })

  it('drafts a reply with the AI and marks it', async () => {
    const drafts: Record<string, unknown>[] = []
    server.use(
      http.post('/api/v1/ai/draft-reply/', async ({ request }) => {
        drafts.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ text: 'Claro, Laura: te dejamos dos toallas en recepción.', simulated: false })
      }),
    )
    const replies = captureReply()
    const { user } = renderWithProviders(
      <Composer conversation={makeConversation()} lastInbound={makeMessage({ body: '¿Tienen toallas?' })} />,
    )

    await user.click(await screen.findByRole('button', { name: 'Borrador IA' }))

    const box = screen.getByRole('textbox', { name: 'Responder' })
    await waitFor(() => expect(box).toHaveValue('Claro, Laura: te dejamos dos toallas en recepción.'))
    expect(drafts).toEqual([{ guest_message: '¿Tienen toallas?', reservation_code: 'HT-LAURA1', language: 'es' }])
    expect(screen.getByText('Borrador de la IA: revísalo antes de enviarlo.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Enviar por WhatsApp' }))
    await waitFor(() => expect(replies).toHaveLength(1))
    expect(replies[0]).toMatchObject({ ai_generated: true })
  })

  it('hides the AI draft when the AI module is not installed (404)', async () => {
    server.use(
      http.post('/api/v1/ai/draft-reply/', () => HttpResponse.json({ detail: 'No encontrado', code: 'not_found' }, { status: 404 })),
    )
    const { user } = renderWithProviders(
      <Composer conversation={makeConversation()} lastInbound={makeMessage({ body: '¿Tienen toallas?' })} />,
    )

    await user.click(await screen.findByRole('button', { name: 'Borrador IA' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Borrador IA' })).not.toBeInTheDocument())
  })

  it('only leaves notes on OTA threads', async () => {
    renderWithProviders(<Composer conversation={makeConversation({ channel: 'ota', address: 'booksim:1' })} />)
    expect(await screen.findByText(/Responde a este huésped desde la extranet del canal/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Responder' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Guardar nota' })).toBeInTheDocument()
  })

  it('is read-only without the send permission', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['messaging.view'], 'reader')] }))
    renderWithProviders(<Composer conversation={makeConversation()} />)
    expect(await screen.findByText('Tienes acceso de solo lectura a la bandeja.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
