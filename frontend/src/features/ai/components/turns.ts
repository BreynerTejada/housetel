import type { CopilotAction, CopilotMessage } from '../api'

const READ_TOOLS = new Set([
  'get_today_summary',
  'list_arrivals',
  'list_departures',
  'search_reservations',
  'get_reservation',
  'check_availability',
  'get_occupancy',
  'find_guest',
  'get_balance',
  'list_alerts',
  'get_rates',
])

interface TurnView {
  key: string
  question: CopilotMessage | null
  consulted: string[]
  answers: CopilotMessage[]
  actions: CopilotAction[]
}

/** Messages grouped by question: what was asked, which data was read, the answers and the proposals. */
export function toTurns(messages: CopilotMessage[], actions: CopilotAction[]): TurnView[] {
  const turns: TurnView[] = []
  const turnOfMessage = new Map<string, TurnView>()
  for (const message of messages) {
    if (message.role === 'user' || turns.length === 0) {
      turns.push({ key: message.id, question: message.role === 'user' ? message : null, consulted: [], answers: [], actions: [] })
      if (message.role === 'user') continue
    }
    const turn = turns[turns.length - 1]!
    turnOfMessage.set(message.id, turn)
    if (message.role !== 'assistant') continue
    for (const call of message.tool_calls) {
      if (READ_TOOLS.has(call.name) && !turn.consulted.includes(call.name)) turn.consulted.push(call.name)
    }
    if (message.content.trim()) turn.answers.push(message)
  }
  for (const action of actions) {
    const turn = (action.message_id && turnOfMessage.get(action.message_id)) || turns[turns.length - 1]
    turn?.actions.push(action)
  }
  return turns
}

