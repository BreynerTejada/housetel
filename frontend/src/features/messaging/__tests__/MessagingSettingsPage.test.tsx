import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, auroraProperty, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import MessagingSettingsPage from '../pages/MessagingSettingsPage'
import type { EffectiveTemplate } from '../api'
import { makeRules, makeTemplates, VARIABLES } from './fixtures'

const TEMPLATES = '/api/v1/messaging/templates/'

function servePage(templates: EffectiveTemplate[] = makeTemplates()) {
  const created: Record<string, unknown>[] = []
  const deleted: string[] = []
  const previews: Record<string, unknown>[] = []
  const patchedRules: [string, Record<string, unknown>][] = []
  server.use(
    http.get(TEMPLATES, () => HttpResponse.json(templates)),
    http.get('/api/v1/messaging/variables/', () => HttpResponse.json(VARIABLES)),
    http.get('/api/v1/messaging/lifecycle-rules/', () => HttpResponse.json(makeRules())),
    http.post(`${TEMPLATES}preview/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      previews.push(body)
      return HttpResponse.json({
        channel: body.channel, language: 'es', source: 'draft', sample: true, subject: 'Reserva confirmada · HT-7K2M9Q',
        text: 'Hola Ana', whatsapp: 'Hola Ana', markup: 'Hola Ana', html: '<p>Hola Ana</p>', missing: [], unknown: [],
      })
    }),
    http.post(TEMPLATES, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      created.push(body)
      return HttpResponse.json({ id: 'new-row', label: { es: 'x', en: 'x' }, updated_at: '2026-09-27T10:00:00Z', ...body }, { status: 201 })
    }),
    http.delete(`${TEMPLATES}:id/`, ({ params }) => {
      deleted.push(String(params.id))
      return new HttpResponse(null, { status: 204 })
    }),
    http.patch('/api/v1/messaging/lifecycle-rules/:id/', async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patchedRules.push([String(params.id), body])
      const rule = makeRules().find((item) => item.id === params.id)!
      return HttpResponse.json({ ...rule, ...body })
    }),
  )
  return { created, deleted, previews, patchedRules }
}

beforeEach(() => {
  useSession.setState({ propertyId: auroraProperty.id, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
  mockMe(makeMe())
})

describe('MessagingSettingsPage · templates', () => {
  it('customizes the Housetel text for this hotel, inserting a variable where the cursor is', async () => {
    const { created, previews } = servePage()
    const { user } = renderWithProviders(<MessagingSettingsPage />)

    const editor = await screen.findByRole('form', { name: 'Confirmación de reserva' })
    expect(within(editor).getByText('Texto de Housetel')).toBeInTheDocument()
    const body = within(editor).getByRole<HTMLTextAreaElement>('textbox', { name: 'Mensaje' })
    await user.clear(body)
    await user.type(body, 'Hola , te esperamos.')
    body.setSelectionRange(5, 5)
    await user.click(within(editor).getByRole('button', { name: 'Insertar variable' }))
    await user.click(await screen.findByRole('menuitem', { name: /Nombre del huésped/ }))
    expect(body).toHaveValue('Hola {{guest.first_name}}, te esperamos.')
    await waitFor(() => expect(previews.at(-1)).toMatchObject({ channel: 'email', body: 'Hola {{guest.first_name}}, te esperamos.' }))

    await user.click(within(editor).getByRole('button', { name: 'Guardar plantilla' }))

    await waitFor(() => expect(created).toHaveLength(1))
    expect(created[0]).toEqual({
      code: 'confirmation',
      channel: 'email',
      language: 'es',
      scope: 'property',
      subject: 'Reserva confirmada · {{reservation.code}}',
      body: 'Hola {{guest.first_name}}, te esperamos.',
      is_active: true,
      wa_template_name: '',
      wa_template_params: [],
    })
  })

  it('edits the WhatsApp text in English of another template', async () => {
    const { created } = servePage()
    const { user } = renderWithProviders(<MessagingSettingsPage />)

    await user.click(await screen.findByRole('button', { name: /Link de pago/ }))
    const editor = await screen.findByRole('form', { name: 'Link de pago' })
    await user.click(within(editor).getByRole('radio', { name: 'WhatsApp' }))
    await user.click(within(editor).getByRole('radio', { name: 'Inglés' }))
    expect(within(editor).queryByRole('textbox', { name: 'Asunto' })).not.toBeInTheDocument()
    const body = within(editor).getByRole('textbox', { name: 'Mensaje' })
    await user.clear(body)
    await user.type(body, 'Pay here')
    await user.click(within(editor).getByRole('button', { name: 'Guardar plantilla' }))

    await waitFor(() => expect(created).toHaveLength(1))
    expect(created[0]).toMatchObject({ code: 'payment_link', channel: 'whatsapp', language: 'en', body: 'Pay here', subject: '' })
  })

  it('goes back to the inherited text by deleting this hotel’s version', async () => {
    const templates = makeTemplates().map((row) =>
      row.key === 'confirmation:email:es'
        ? { ...row, source: 'property' as const, id: 'row-1', property_template_id: 'row-1', body: 'Versión del hotel' }
        : row,
    )
    const { deleted } = servePage(templates)
    const { user } = renderWithProviders(<MessagingSettingsPage />)

    const editor = await screen.findByRole('form', { name: 'Confirmación de reserva' })
    expect(within(editor).getByText('De este hotel')).toBeInTheDocument()
    await user.click(within(editor).getByRole('button', { name: 'Volver al texto heredado' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Volver al texto heredado?' })
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(deleted).toEqual(['row-1']))
  })

  it('creates a custom template with a code derived from its name', async () => {
    const { created } = servePage()
    const { user } = renderWithProviders(<MessagingSettingsPage />)

    await user.click(await screen.findByRole('button', { name: 'Nueva plantilla' }))
    const dialog = await screen.findByRole('dialog', { name: 'Nueva plantilla personalizada' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Nombre' }), 'Oferta de spa')
    expect(within(dialog).getByRole('textbox', { name: 'Código' })).toHaveValue('oferta_de_spa')
    await user.click(within(dialog).getByRole('button', { name: 'Crear plantilla' }))

    await waitFor(() => expect(created).toHaveLength(1))
    expect(created[0]).toMatchObject({ code: 'oferta_de_spa', name: 'Oferta de spa', channel: 'whatsapp', language: 'es', scope: 'property' })
  })

  it('shows the settings read-only without the templates permission', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['messaging.view'], 'reader')] }))
    servePage()
    renderWithProviders(<MessagingSettingsPage />)

    expect(await screen.findByText(/Puedes ver la configuración, pero no cambiarla/)).toBeInTheDocument()
    const editor = await screen.findByRole('form', { name: 'Confirmación de reserva' })
    expect(within(editor).getByRole('button', { name: 'Guardar plantilla' })).toBeDisabled()
  })
})

describe('MessagingSettingsPage · automatic messages', () => {
  it('turns a message off and changes when it goes out', async () => {
    const { patchedRules } = servePage()
    const { user } = renderWithProviders(<MessagingSettingsPage />, { route: '/?tab=rules' })

    const postStay = await screen.findByRole('group', { name: 'Después de la estadía' })
    expect(within(postStay).getByText('1 día después de la salida, para pedir su opinión.')).toBeInTheDocument()
    await user.click(within(postStay).getByRole('switch', { name: 'Activo' }))
    await waitFor(() => expect(patchedRules).toContainEqual(['r4', { enabled: false }]))

    const offset = within(postStay).getByRole('spinbutton', { name: 'Días después de la salida' })
    await user.clear(offset)
    await user.type(offset, '2')
    await user.tab()
    await waitFor(() => expect(patchedRules).toContainEqual(['r4', { days_offset: 2 }]))

    await user.click(within(postStay).getByRole('checkbox', { name: 'WhatsApp' }))
    await waitFor(() => expect(patchedRules).toContainEqual(['r4', { channels: ['email', 'whatsapp'] }]))
  })
})
