import { Sparkles } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'
import { useCopilotStore } from './store'

// ⌘K: "Ask the copilot…" opens the panel and sends what was typed in the palette (if anything).
export const commands: CommandItem[] = [
  {
    id: 'ai-ask-copilot',
    group: 'ai:commands.group',
    labelKey: 'ai:commands.ask',
    icon: Sparkles,
    keywords: ['copiloto', 'copilot', 'ia', 'ai', 'preguntar', 'ask', 'asistente', 'assistant'],
    permission: 'ai.copilot',
    perform: ({ query }) => useCopilotStore.getState().ask(query),
  },
]
