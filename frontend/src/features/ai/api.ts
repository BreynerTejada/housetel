/**
 * AI API client (backend `apps/ai`, docs/integration-notes/C9-ai.md): copilot, settings, FAQ, usage,
 * chatbot conversations, assisted onboarding and the public chatbot. Money is a decimal string.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, publicApi } from '@/lib/api'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---- copilot --------------------------------------------------------------------------------------

export type CopilotRole = 'user' | 'assistant' | 'tool'
export type ActionStatus = 'proposed' | 'executed' | 'rejected' | 'failed'
export type CopilotActionCode =
  | 'create_reservation'
  | 'move_room'
  | 'check_in'
  | 'check_out'
  | 'send_message'
  | 'block_room'
  | 'add_extra'

export interface ToolCallRef {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface CopilotMessage {
  id: string
  role: CopilotRole
  content: string
  tool_calls: ToolCallRef[]
  tool_call_id: string
  name: string
  provider: string
  simulated: boolean
  created_at: string
}

export interface CopilotAction {
  id: string
  action: CopilotActionCode | string
  summary: string
  details: Record<string, unknown>
  status: ActionStatus
  permission: string
  result: Record<string, unknown>
  error: string
  message_id: string | null
  created_at: string
  decided_at: string | null
  executed_at: string | null
}

export interface CopilotSession {
  id: string
  title: string
  created_at: string
  last_message_at: string | null
}

export interface CopilotSessionDetail extends CopilotSession {
  messages: CopilotMessage[]
  actions: CopilotAction[]
}

export interface CopilotTurn {
  session: CopilotSession
  messages: CopilotMessage[]
  proposals: CopilotAction[]
}

export interface CopilotStatus {
  enabled: boolean
  effective: 'real' | 'simulated'
  provider_label: string
  suggestions: string[]
}

export const aiKeys = {
  all: ['ai'] as const,
  copilotStatus: (lang: string) => ['ai', 'copilot', 'status', lang] as const,
  sessions: () => ['ai', 'copilot', 'sessions'] as const,
  session: (id: string) => ['ai', 'copilot', 'session', id] as const,
  settings: () => ['ai', 'settings'] as const,
  faqs: (language?: string) => ['ai', 'faqs', language ?? 'all'] as const,
  usage: (days: number) => ['ai', 'usage', days] as const,
  conversations: (filter: string) => ['ai', 'conversations', filter] as const,
  conversation: (id: string) => ['ai', 'conversation', id] as const,
}

const COPILOT = '/ai/copilot'

export const getCopilotStatus = (language: string) =>
  api.get<CopilotStatus>(`${COPILOT}/status/`, { params: { language } })
export const listSessions = () => api.get<Page<CopilotSession>>(`${COPILOT}/sessions/`, { params: { page_size: 20 } })
export const getSession = (id: string) => api.get<CopilotSessionDetail>(`${COPILOT}/sessions/${id}/`)
export const createSession = () => api.post<CopilotSessionDetail>(`${COPILOT}/sessions/`, {})
export const deleteSession = (id: string) => api.delete(`${COPILOT}/sessions/${id}/`)
export const askCopilot = (id: string, message: string, language: string) =>
  api.post<CopilotTurn>(`${COPILOT}/sessions/${id}/messages/`, { message, language })
export const confirmAction = (id: string) => api.post<CopilotAction>(`${COPILOT}/actions/${id}/confirm/`, {})
export const rejectAction = (id: string) => api.post<CopilotAction>(`${COPILOT}/actions/${id}/reject/`, {})

export function useCopilotStatus(language: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.copilotStatus(language),
    queryFn: () => getCopilotStatus(language),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useCopilotSessions(enabled = true) {
  return useQuery({ queryKey: aiKeys.sessions(), queryFn: listSessions, enabled })
}

/** A conversation; the panel updates its cache after every turn, so it never refetches on its own. */
export function useCopilotSession(id: string | null) {
  return useQuery({
    queryKey: aiKeys.session(id ?? 'none'),
    queryFn: () => getSession(id as string),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

// ---- settings, FAQ, usage, conversations ------------------------------------------------------------

export type Lang = 'es' | 'en'

export interface ProviderInfo {
  mode: 'real' | 'simulated'
  enabled: boolean
  provider: 'gemini' | 'claude'
  label: string
  /** Model in use (the hotel's own, or the platform's when unset). */
  model: string
  custom_model: string
  platform_model: string
  effective: 'real' | 'simulated'
  effective_label: string
  platform_key_configured: boolean
  own_key_configured: boolean
  status: { error?: string; at?: string; cooling_down_until?: string; last_success_at?: string }
  providers: { value: 'gemini' | 'claude'; label: string; platform_key_configured: boolean }[]
}

export interface AISettings {
  copilot_enabled: boolean
  chatbot_enabled: boolean
  draft_replies_enabled: boolean
  chatbot_greeting: Record<Lang, string>
  provider: ProviderInfo
}

export interface AISettingsInput {
  copilot_enabled?: boolean
  chatbot_enabled?: boolean
  draft_replies_enabled?: boolean
  chatbot_greeting?: Record<Lang, string>
  mode?: 'real' | 'simulated'
  provider?: 'gemini' | 'claude'
  model?: string
}

export interface FAQ {
  id: string
  question: string
  answer: string
  language: Lang
  sort: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type FAQInput = Pick<FAQ, 'question' | 'answer' | 'language'> & Partial<Pick<FAQ, 'sort' | 'is_active'>>

export interface UsageGroup {
  calls: number
  errors: number
  simulated: number
}

export interface UsageReport {
  since: string
  days: number
  totals: UsageGroup & { input_tokens: number; output_tokens: number; avg_latency_ms: number; real: number }
  by_feature: (UsageGroup & { feature: string })[]
  by_provider: (UsageGroup & { provider: string })[]
  by_day: (UsageGroup & { date: string })[]
  recent_errors: { at: string; feature: string; provider: string; error: string }[]
}

export interface ChatCard {
  type: 'offer'
  room_type_id: string
  room_type_code: string
  room_type: string
  rate_plan: string
  total: string
  per_night: string
  currency: string
  available: number
  nights: number
  checkin: string
  checkout: string
  adults: number
  children: number
  url: string
}

export interface ChatEntry {
  role: 'user' | 'assistant'
  content: string
  cards: ChatCard[]
  at: string | null
}

export interface ChatContact {
  name?: string
  email?: string
  phone?: string
  message?: string
}

export interface ChatbotConversation {
  id: string
  language: Lang
  handoff_requested: boolean
  handoff_reason: string
  handoff_at: string | null
  handoff_resolved_at: string | null
  contact: ChatContact
  reservation: { id: string; code: string } | null
  messages_count: number
  last_message: string
  last_message_at: string | null
  created_at: string
}

export interface ChatbotConversationDetail extends ChatbotConversation {
  messages: ChatEntry[]
}

export type ConversationFilter = 'all' | 'handoff' | 'open'

export const getSettings = () => api.get<AISettings>('/ai/settings/')
export const updateSettings = (input: AISettingsInput) => api.patch<AISettings>('/ai/settings/', input)
export const listFaqs = (language?: Lang) =>
  api.get<Page<FAQ>>('/ai/faqs/', { params: { language, page_size: 200 } })
export const createFaq = (input: FAQInput) => api.post<FAQ>('/ai/faqs/', input)
export const updateFaq = (id: string, input: Partial<FAQInput>) => api.patch<FAQ>(`/ai/faqs/${id}/`, input)
export const deleteFaq = (id: string) => api.delete(`/ai/faqs/${id}/`)
export const getUsage = (days: number) => api.get<UsageReport>('/ai/usage/', { params: { days } })
export const listConversations = (filter: ConversationFilter) =>
  api.get<Page<ChatbotConversation>>('/ai/chatbot-conversations/', {
    params: { handoff: filter === 'handoff' ? '1' : undefined, open: filter === 'open' ? '1' : undefined, page_size: 50 },
  })
export const getConversation = (id: string) => api.get<ChatbotConversationDetail>(`/ai/chatbot-conversations/${id}/`)
export const resolveConversation = (id: string) =>
  api.post<ChatbotConversationDetail>(`/ai/chatbot-conversations/${id}/resolve/`, {})

export function useAISettings() {
  return useQuery({ queryKey: aiKeys.settings(), queryFn: getSettings })
}

export function useUpdateAISettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(aiKeys.settings(), data)
      void queryClient.invalidateQueries({ queryKey: ['ai', 'copilot', 'status'] })
    },
  })
}

export function useFaqs(language?: Lang) {
  return useQuery({ queryKey: aiKeys.faqs(language), queryFn: () => listFaqs(language) })
}

export function useUsage(days = 30) {
  return useQuery({ queryKey: aiKeys.usage(days), queryFn: () => getUsage(days) })
}

export function useConversations(filter: ConversationFilter) {
  return useQuery({ queryKey: aiKeys.conversations(filter), queryFn: () => listConversations(filter) })
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: aiKeys.conversation(id ?? 'none'),
    queryFn: () => getConversation(id as string),
    enabled: Boolean(id),
  })
}

// ---- onboarding -------------------------------------------------------------------------------------

export type RoomKind = 'private' | 'dorm'
export type BedType = 'single' | 'twin' | 'double' | 'queen' | 'king' | 'bunk' | 'sofa_bed' | 'crib'
export type ChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'

export interface ProposalRoomType {
  code: string
  name: Record<Lang, string>
  kind: RoomKind
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  beds: { type: BedType; count: number }[]
  beds_per_room: number | null
  size_m2: number | null
  amenities: string[]
  units: number
  room_numbers: string[]
  base_price: string
  weekend_adjust_percent: number
  extra_adult_price: string
  extra_child_price: string
}

export interface Proposal {
  property: {
    name: string
    description: Record<Lang, string>
    city: string
    address: string
    phone: string
    email: string
    star_rating: number | null
    check_in_time: string | null
    check_out_time: string | null
    amenities: string[]
  }
  room_types: ProposalRoomType[]
  policies: {
    non_refundable_discount_percent: number
    breakfast_price: string | null
    pets_allowed: boolean
    smoking_allowed: boolean
    children_allowed: boolean
  }
  extras: { code: string; name: Record<Lang, string>; price: string; charge_type: ChargeType }[]
}

export interface ProposalResponse {
  proposal: Proposal
  warnings: string[]
  simulated: boolean
  provider: string
  website: { url: string; fetched: boolean; chars: number; error: string } | null
}

export interface OnboardingSummary {
  room_types: { id: string; code: string; name: Record<Lang, string>; kind: RoomKind; rooms: string[] }[]
  rooms_created: number
  rate_plans: string[]
  extras: string[]
  profile_updated: string[]
  links: Record<'room_types' | 'rooms' | 'rates' | 'plans' | 'property' | 'extras', string>
}

export const proposeOnboarding = (input: { description: string; website_url: string }) =>
  api.post<ProposalResponse>('/ai/onboarding/propose/', input)
/** Same proposal made consistent by the backend (unique codes and room numbers), without the model. */
export const normalizeOnboarding = (proposal: Proposal) =>
  api.post<{ proposal: Proposal; warnings: string[] }>('/ai/onboarding/normalize/', { proposal })
export const applyOnboarding = (proposal: Proposal) =>
  api.post<OnboardingSummary>('/ai/onboarding/apply/', { proposal })

export interface AmenityRef {
  id: string
  code: string
  name: Record<Lang, string>
  category: string
}

/** Amenity names for the codes of a proposal (inventory catalog: global + the organization's own). */
export function useAmenityNames(enabled = true) {
  return useQuery({
    queryKey: ['ai', 'amenity-names'],
    queryFn: () => api.get<AmenityRef[]>('/inventory/amenities/'),
    enabled,
    staleTime: 10 * 60_000,
    select: (items) => new Map(items.map((item) => [item.code, item.name])),
  })
}

// ---- public chatbot ----------------------------------------------------------------------------------

export interface Handoff {
  requested: boolean
  contact_needed: boolean
  contact_received: boolean
}

export interface ChatConfig {
  enabled: boolean
  property: { name: string; slug: string; city: string; primary_color: string }
  greeting: string
  suggestions: string[]
  languages: Lang[]
  session_id: string | null
  messages: ChatEntry[]
  handoff: Handoff | null
}

export interface ChatReply {
  session_id: string
  reply: ChatEntry
  handoff: Handoff
}

export type ChatTarget = { propertySlug: string; portalToken?: undefined } | { portalToken: string; propertySlug?: undefined }

export function chatBase(target: ChatTarget): string {
  return target.portalToken
    ? `/ai/portal-chat/${encodeURIComponent(target.portalToken)}`
    : `/ai/chat/${encodeURIComponent(target.propertySlug as string)}`
}

export const getChatConfig = (target: ChatTarget, language: string, sessionId: string | null) =>
  publicApi.get<ChatConfig>(`${chatBase(target)}/`, { params: { language, session_id: sessionId } })
export const sendChat = (target: ChatTarget, input: { message: string; language: string; session_id?: string | null }) =>
  publicApi.post<ChatReply>(`${chatBase(target)}/`, { ...input, session_id: input.session_id || undefined })
export const sendChatContact = (
  target: ChatTarget,
  input: { session_id: string; name: string; email: string; phone: string; message: string },
) => publicApi.post<{ ok: boolean; handoff: Handoff }>(`${chatBase(target)}/contact/`, input)
