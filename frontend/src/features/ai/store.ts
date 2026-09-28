import { create } from 'zustand'

/**
 * Copilot panel state shared by the topbar button, the ⌘K command and the panel itself.
 * The conversation is remembered per property (a session belongs to one hotel), in memory only.
 */
interface CopilotState {
  open: boolean
  /** Question to send as soon as the panel is ready (⌘K "Ask the copilot…"). */
  pending: string | null
  sessions: Record<string, string>
  setOpen: (open: boolean) => void
  toggle: () => void
  /** Opens the panel; with a question it is sent right away. */
  ask: (question?: string) => void
  takePending: () => string | null
  setSession: (propertyId: string, sessionId: string | null) => void
}

export const useCopilotStore = create<CopilotState>()((set, get) => ({
  open: false,
  pending: null,
  sessions: {},
  setOpen: (open) => set({ open }),
  toggle: () => set((state) => ({ open: !state.open })),
  ask: (question) => set({ open: true, pending: question?.trim() ? question.trim() : null }),
  takePending: () => {
    const { pending } = get()
    if (pending) set({ pending: null })
    return pending
  },
  setSession: (propertyId, sessionId) =>
    set((state) => {
      const sessions = { ...state.sessions }
      if (sessionId) sessions[propertyId] = sessionId
      else delete sessions[propertyId]
      return { sessions }
    }),
}))
