import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { commands } from '../commands'
import { CopilotPanel } from '../components/CopilotPanel'
import { useCopilotStore } from '../store'
import type { CopilotAction, CopilotMessage, CopilotTurn } from '../api'

const BASE = '/api/v1/ai/copilot'
const NOW = '2026-09-25T10:00:00-05:00'

function message(overrides: Partial<CopilotMessage>): CopilotMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    tool_calls: [],
    tool_call_id: '',
    name: '',
    provider: 'simulated',
    simulated: true,
    created_at: NOW,
    ...overrides,
  }
}

function proposal(overrides: Partial<CopilotAction> = {}): CopilotAction {
  return {
    id: 'action-1',
    action: 'move_room',
    summary: 'Mover HT-AAAAAA (Laura Gómez) de la 101 a la 102',
    details: {
      code: 'HT-AAAAAA', guest: 'Laura Gómez', from_room: '101', to_room: '102', checkin: '2026-09-26',
      checkout: '2026-09-28', reservation_id: 'res-1', category_change: false,
    },
    status: 'proposed',
    permission: 'bookings.manage',
    result: {},
    error: '',
    message_id: null,
    created_at: NOW,
    decided_at: null,
    executed_at: null,
    ...overrides,
  }
}

function turn(question: string, answer: string, { tool = 'list_arrivals', proposals = [] as CopilotAction[] } = {}): CopilotTurn {
  const caller = message({ tool_calls: [{ id: 'c1', name: tool, arguments: {} }] })
  for (const item of proposals) item.message_id = caller.id
  return {
    session: { id: 'session-1', title: question, created_at: NOW, last_message_at: NOW },
    messages: [
      message({ role: 'user', content: question, provider: '', simulated: false }),
      caller,
      message({ role: 'tool', name: tool, tool_call_id: 'c1', content: '{}' }),
      message({ content: answer }),
    ],
    proposals,
  }
}

interface Served {
  asked: { message: string; language: string }[]
  confirmed: string[]
}

function serveCopilot({ turns, confirm }: { turns: CopilotTurn[]; confirm?: (id: string) => Response }): Served {
  const served: Served = { asked: [], confirmed: [] }
  let index = 0
  server.use(
    http.get(`${BASE}/status/`, () =>
      HttpResponse.json({
        enabled: true,
        effective: 'simulated',
        provider_label: 'Simulado',
        suggestions: ['¿Cuántas llegadas hay hoy?', '¿Cómo va la ocupación esta semana?'],
      }),
    ),
    http.get(`${BASE}/sessions/`, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    http.post(`${BASE}/sessions/`, () =>
      HttpResponse.json(
        { id: 'session-1', title: '', created_at: NOW, last_message_at: null, messages: [], actions: [] },
        { status: 201 },
      ),
    ),
    http.get(`${BASE}/sessions/session-1/`, () =>
      HttpResponse.json({ id: 'session-1', title: '', created_at: NOW, last_message_at: null, messages: [], actions: [] }),
    ),
    http.post(`${BASE}/sessions/session-1/messages/`, async ({ request }) => {
      served.asked.push((await request.json()) as Served['asked'][number])
      const next = turns[Math.min(index, turns.length - 1)]!
      index += 1
      return HttpResponse.json(next)
    }),
    http.post(`${BASE}/actions/:id/confirm/`, ({ params }) => {
      served.confirmed.push(String(params.id))
      return confirm ? confirm(String(params.id)) : HttpResponse.json(proposal({ status: 'executed', executed_at: NOW }))
    }),
    http.post(`${BASE}/actions/:id/reject/`, () => HttpResponse.json(proposal({ status: 'rejected', decided_at: NOW }))),
  )
  return served
}

function renderPanel() {
  return renderWithProviders(<CopilotPanel open onOpenChange={() => undefined} />)
}

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  useCopilotStore.setState({ open: true, pending: null, sessions: {} })
  document.cookie = 'csrftoken=t; path=/'
})

describe('CopilotPanel', () => {
  it('answers a suggested question and says which hotel data it used', async () => {
    mockMe(makeMe())
    const served = serveCopilot({ turns: [turn('¿Cuántas llegadas hay hoy?', 'Hoy hay **1 llegada**: HT-AAAAAA.')] })
    const { user } = renderPanel()

    expect(await screen.findByText('Modo simulado')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: '¿Cuántas llegadas hay hoy?' }))

    const answer = await screen.findByText(/HT-AAAAAA/)
    expect(within(answer.closest('p') as HTMLElement).getByText('1 llegada').tagName).toBe('STRONG')
    expect(screen.getByText('Consultó: llegadas')).toBeInTheDocument()
    expect(served.asked).toEqual([{ message: '¿Cuántas llegadas hay hoy?', language: 'es' }])
  })

  it('sends what the user types with Enter and keeps the conversation for the next question', async () => {
    mockMe(makeMe())
    const served = serveCopilot({
      turns: [turn('¿Salidas de hoy?', 'Hoy salen 2 reservas.', { tool: 'list_departures' }), turn('¿Y mañana?', 'Mañana sale 1.')],
    })
    const { user } = renderPanel()

    const box = await screen.findByRole('textbox', { name: 'Pregunta al copiloto' })
    await user.type(box, '¿Salidas de hoy?{Enter}')
    expect(await screen.findByText('Hoy salen 2 reservas.')).toBeInTheDocument()
    await user.type(box, '¿Y mañana?{Enter}')

    expect(await screen.findByText('Mañana sale 1.')).toBeInTheDocument()
    expect(screen.getByText('Hoy salen 2 reservas.')).toBeInTheDocument()
    expect(served.asked.map((item) => item.message)).toEqual(['¿Salidas de hoy?', '¿Y mañana?'])
  })

  it('shows an action as a proposal and runs it only after the user confirms', async () => {
    mockMe(makeMe())
    const served = serveCopilot({
      turns: [
        turn('Mueve HT-AAAAAA a la 102', 'Preparé el cambio: confírmalo en la tarjeta.', {
          tool: 'move_room',
          proposals: [proposal()],
        }),
      ],
    })
    const { user } = renderPanel()

    const box = await screen.findByRole('textbox', { name: 'Pregunta al copiloto' })
    await user.type(box, 'Mueve HT-AAAAAA a la 102{Enter}')

    const card = await screen.findByRole('article', { name: /Mover de habitación/ })
    expect(within(card).getByText('Mover HT-AAAAAA (Laura Gómez) de la 101 a la 102')).toBeInTheDocument()
    expect(within(card).getByText('102')).toBeInTheDocument()
    expect(served.confirmed).toEqual([])

    await user.click(within(card).getByRole('button', { name: 'Confirmar' }))

    expect(await within(card).findByText('Ejecutada')).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Confirmar' })).not.toBeInTheDocument()
    expect(served.confirmed).toEqual(['action-1'])
  })

  it('explains why a confirmed action could not run', async () => {
    mockMe(makeMe())
    serveCopilot({
      turns: [turn('Mueve HT-AAAAAA a la 102', 'Listo para confirmar.', { tool: 'move_room', proposals: [proposal()] })],
      confirm: () => HttpResponse.json(proposal({ status: 'failed', error: 'La habitación ya está ocupada en esas fechas' })),
    })
    const { user } = renderPanel()

    await user.type(await screen.findByRole('textbox', { name: 'Pregunta al copiloto' }), 'Mueve HT-AAAAAA{Enter}')
    const card = await screen.findByRole('article', { name: /Mover de habitación/ })
    await user.click(within(card).getByRole('button', { name: 'Confirmar' }))

    expect(await within(card).findByText('La habitación ya está ocupada en esas fechas')).toBeInTheDocument()
    expect(within(card).getByText('No se pudo ejecutar')).toBeInTheDocument()
  })

  it('tells the user when the role no longer allows the action', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['ai.copilot', 'bookings.view'], 'custom')] }))
    serveCopilot({
      turns: [turn('Mueve HT-AAAAAA a la 102', 'Listo para confirmar.', { tool: 'move_room', proposals: [proposal()] })],
      confirm: () =>
        HttpResponse.json(
          { detail: 'Ya no tienes permiso para ejecutar esta acción', code: 'permission_denied', permission: 'bookings.manage' },
          { status: 403 },
        ),
    })
    const { user } = renderPanel()

    await user.type(await screen.findByRole('textbox', { name: 'Pregunta al copiloto' }), 'Mueve HT-AAAAAA{Enter}')
    const card = await screen.findByRole('article', { name: /Mover de habitación/ })
    await user.click(within(card).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('Ya no tienes permiso para ejecutar esta acción')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
  })

  it('discards a proposal without running it', async () => {
    mockMe(makeMe())
    const served = serveCopilot({
      turns: [turn('Mueve HT-AAAAAA a la 102', 'Listo para confirmar.', { tool: 'move_room', proposals: [proposal()] })],
    })
    const { user } = renderPanel()

    await user.type(await screen.findByRole('textbox', { name: 'Pregunta al copiloto' }), 'Mueve HT-AAAAAA{Enter}')
    const card = await screen.findByRole('article', { name: /Mover de habitación/ })
    await user.click(within(card).getByRole('button', { name: 'Descartar' }))

    expect(await within(card).findByText('Descartada')).toBeInTheDocument()
    expect(served.confirmed).toEqual([])
  })
})

describe('Ask the copilot (⌘K)', () => {
  it('opens the panel and sends what was typed in the palette', async () => {
    mockMe(makeMe())
    const served = serveCopilot({ turns: [turn('¿Cuántas llegadas hay hoy?', 'Hoy hay 3 llegadas.')] })
    useCopilotStore.setState({ open: false, pending: null })
    const command = commands.find((item) => item.id === 'ai-ask-copilot')!

    act(() => command.perform({ navigate: () => undefined, query: '¿Cuántas llegadas hay hoy?' }))
    renderPanel()

    expect(useCopilotStore.getState().open).toBe(true)
    expect(await screen.findByText('Hoy hay 3 llegadas.')).toBeInTheDocument()
    await waitFor(() => expect(served.asked.map((item) => item.message)).toEqual(['¿Cuántas llegadas hay hoy?']))
    expect(command.permission).toBe('ai.copilot')
  })
})
