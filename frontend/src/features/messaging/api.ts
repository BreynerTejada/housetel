/**
 * Messaging API client (backend `apps/messaging`, docs/integration-notes/C6-messaging.md): the unified inbox,
 * templates, lifecycle rules, "write to a guest" and the WhatsApp simulator. Other features may reuse the
 * types and hooks (e.g. `useConversations({ reservation })` in a reservation tab).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Member } from '@/features/team/api'
import { api, isApiError } from '@/lib/api'

export type Channel = 'email' | 'whatsapp' | 'web_chat' | 'ota'
export type SendChannel = 'email' | 'whatsapp'
export type MessageChannel = Channel | 'internal_note'
export type MessageStatus = 'queued' | 'sent' | 'delivered' | 'read' | 'failed' | 'received'
export type ConversationStatus = 'open' | 'closed'
export type Language = 'es' | 'en'
export type TemplateSource = 'system' | 'organization' | 'property'
export type LifecycleEvent =
  | 'confirmation'
  | 'pre_arrival'
  | 'arrival_day'
  | 'post_stay'
  | 'payment_reminder'
  | 'cancellation'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface I18nText {
  es: string
  en: string
}

export interface UserRef {
  id: string
  full_name: string
  email: string
}

export interface GuestRef {
  id: string
  full_name: string
  email: string
  phone: string
  language: string
  is_vip: boolean
}

export interface ReservationRef {
  id: string
  code: string
  status: string
  checkin_date: string
  checkout_date: string
  /** Room (and bed) of the first active stay with a unit: "301", "D1 · A" or "". */
  room?: string
}

export interface Conversation {
  id: string
  channel: Channel
  status: ConversationStatus
  contact_name: string
  address: string
  display_name: string
  guest: GuestRef | null
  reservation: ReservationRef | null
  assigned_to: UserRef | null
  last_message_at: string | null
  last_message_preview: string
  last_message_direction: 'in' | 'out' | ''
  /** The guest's last message: opens WhatsApp's 24 h window. */
  last_inbound_at: string | null
  unread_count: number
  /** WhatsApp only: the guest wrote in the last 24 h (free text allowed). */
  whatsapp_window_open: boolean | null
  created_at: string
}

export interface ReservationContext {
  id: string
  code: string
  status: string
  source: string
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  currency: string
  total_amount: string
  balance: string
  room_types: string[]
  rooms: string[]
}

export interface GuestContext extends GuestRef {
  first_name: string
  nationality: string
  country_of_residence: string
}

export interface ConversationDetail extends Conversation {
  context: { guest: GuestContext | null; reservation: ReservationContext | null }
}

export interface Message {
  id: string
  direction: 'in' | 'out'
  channel: MessageChannel
  sender_label: string
  recipient: string
  subject: string
  body: string
  status: MessageStatus
  error: string
  template_code: string
  ai_generated: boolean
  sent_by: UserRef | null
  created_at: string
  status_updated_at: string | null
}

export interface MessagePage {
  results: Message[]
  has_more: boolean
}

export interface ConversationFilters {
  unread?: boolean
  channel?: Channel
  status?: ConversationStatus
  assigned?: 'me' | 'none' | string
  reservation?: string
  guest?: string
  q?: string
  page_size?: number
}

export interface ReplyInput {
  body: string
  subject?: string
  internal?: boolean
  template_code?: string
  ai_generated?: boolean
}

export interface EffectiveTemplate {
  key: string
  code: string
  label: I18nText
  is_system_code: boolean
  channel: SendChannel
  language: Language
  source: TemplateSource
  id: string | null
  subject: string
  body: string
  is_active: boolean
  wa_template_name: string
  wa_template_params: string[]
  updated_at: string | null
  organization_template_id: string | null
  property_template_id: string | null
}

export interface TemplateRow {
  id: string
  code: string
  name: string
  label: I18nText
  channel: SendChannel
  language: Language
  scope: 'property' | 'organization'
  subject: string
  body: string
  is_active: boolean
  wa_template_name: string
  wa_template_params: string[]
  updated_at: string
}

export type TemplateInput = Partial<Omit<TemplateRow, 'id' | 'label' | 'updated_at'>>

export interface PreviewInput {
  channel: SendChannel
  language?: Language | null
  template_code?: string
  subject?: string | null
  body?: string | null
  reservation_id?: string | null
  conversation_id?: string | null
  guest_id?: string | null
}

export interface Preview {
  channel: SendChannel
  language: Language
  source: TemplateSource | 'draft'
  sample: boolean
  subject: string
  text: string
  whatsapp: string
  /** Values filled in, markup kept: what the composer inserts. */
  markup: string
  html: string
  missing: string[]
  unknown: string[]
}

export interface Variable {
  key: string
  group: 'guest' | 'reservation' | 'property' | 'links' | 'payment'
  label: I18nText
  example: I18nText
}

export interface LifecycleRule {
  id: string
  event: LifecycleEvent
  label: I18nText
  enabled: boolean
  days_offset: number
  uses_offset: boolean
  channels: SendChannel[]
  template_code: string
  /** "HH:MM", local time of the hotel. */
  send_after: string
  scheduled: boolean
}

export type LifecycleRuleInput = Partial<Pick<LifecycleRule, 'enabled' | 'days_offset' | 'channels' | 'template_code' | 'send_after'>>

export interface SendInput {
  channel: SendChannel
  reservation_id?: string
  guest_id?: string
  to?: string
  template_code?: string
  subject?: string
  body?: string
}

export interface SendResult {
  message: Message
  conversation_id: string
}

/** Who "write to the guest" goes to: the guest, the template language and the address on each channel. */
export interface Recipient {
  guest: { id: string; full_name: string; email: string; phone: string; language: string } | null
  reservation: ReservationRef | null
  language: Language
  /** Normalized address Housetel would use ('' = none: ask for one). */
  addresses: Record<SendChannel, string>
}

export interface RecipientParams {
  reservation?: string
  guest?: string
}

export interface SimulatorThread {
  phone: string
  simulator_enabled: boolean
  conversation_id: string | null
  guest: { id: string; full_name: string; language: string } | null
  messages: Message[]
}

export interface SimulatorContact {
  guest_id: string
  full_name: string
  phone: string
  reservation: ReservationRef | null
}

export interface SimulatorContacts {
  simulator_enabled: boolean
  results: SimulatorContact[]
}

export interface UnreadCount {
  conversations: number
  messages: number
}

// --- keys ------------------------------------------------------------------------------------------

export const messagingKeys = {
  all: ['messaging'] as const,
  conversations: (filters: ConversationFilters = {}) => ['messaging', 'conversations', filters] as const,
  conversation: (id: string) => ['messaging', 'conversation', id] as const,
  messages: (id: string) => ['messaging', 'messages', id] as const,
  unread: ['messaging', 'unread'] as const,
  templates: ['messaging', 'templates'] as const,
  variables: ['messaging', 'variables'] as const,
  rules: ['messaging', 'rules'] as const,
  simulatorThread: (phone: string) => ['messaging', 'simulator', 'thread', phone] as const,
  simulatorContacts: (q: string) => ['messaging', 'simulator', 'contacts', q] as const,
  recipient: (params: RecipientParams) => ['messaging', 'recipient', params] as const,
}

// --- fetchers --------------------------------------------------------------------------------------

const BASE = '/messaging'

export function getConversations(filters: ConversationFilters = {}): Promise<Page<Conversation>> {
  const { unread, ...rest } = filters
  return api.get(`${BASE}/conversations/`, { params: { ...rest, unread: unread ? '1' : undefined } })
}

export const getConversation = (id: string) => api.get<ConversationDetail>(`${BASE}/conversations/${id}/`)

export function getMessages(id: string, params: { limit?: number; before?: string } = {}): Promise<MessagePage> {
  return api.get(`${BASE}/conversations/${id}/messages/`, { params })
}

export const postReply = (id: string, input: ReplyInput) =>
  api.post<Message>(`${BASE}/conversations/${id}/messages/`, input)
export const markRead = (id: string) => api.post<Conversation>(`${BASE}/conversations/${id}/read/`)
export const assignConversation = (id: string, userId: string | null) =>
  api.post<Conversation>(`${BASE}/conversations/${id}/assign/`, { user_id: userId })
export const closeConversation = (id: string) => api.post<Conversation>(`${BASE}/conversations/${id}/close/`)
export const reopenConversation = (id: string) => api.post<Conversation>(`${BASE}/conversations/${id}/reopen/`)
export const getUnreadCount = () => api.get<UnreadCount>(`${BASE}/conversations/unread-count/`)

export const getTemplates = () => api.get<EffectiveTemplate[]>(`${BASE}/templates/`)
export const createTemplate = (input: TemplateInput) => api.post<TemplateRow>(`${BASE}/templates/`, input)
export const updateTemplate = (id: string, input: TemplateInput) => api.patch<TemplateRow>(`${BASE}/templates/${id}/`, input)
export const deleteTemplate = (id: string) => api.delete<void>(`${BASE}/templates/${id}/`)
export const previewTemplate = (input: PreviewInput) => api.post<Preview>(`${BASE}/templates/preview/`, input)
export const getVariables = () => api.get<Variable[]>(`${BASE}/variables/`)

export const getRules = () => api.get<LifecycleRule[]>(`${BASE}/lifecycle-rules/`)
export const updateRule = (id: string, input: LifecycleRuleInput) =>
  api.patch<LifecycleRule>(`${BASE}/lifecycle-rules/${id}/`, input)

export const sendToGuest = (input: SendInput) => api.post<SendResult>(`${BASE}/send/`, input)
export const getRecipient = (params: RecipientParams) => api.get<Recipient>(`${BASE}/recipient/`, { params: { ...params } })

export const getSimulatorThread = (phone: string) =>
  api.get<SimulatorThread>(`${BASE}/simulator/whatsapp/thread/`, { params: { phone } })
export const getSimulatorContacts = (q: string) =>
  api.get<SimulatorContacts>(`${BASE}/simulator/whatsapp/contacts/`, { params: { q } })
export const postSimulatorInbound = (input: { phone: string; body: string; name?: string }) =>
  api.post<SendResult>(`${BASE}/simulator/whatsapp/inbound/`, input)

/** AI draft of a reply (C9, `POST /api/v1/ai/draft-reply/`). A 404 means the AI module is not installed. */
export function draftReply(input: { guest_message: string; reservation_code?: string; language?: string }) {
  return api.post<{ text: string; simulated: boolean }>('/ai/draft-reply/', input)
}

export const isNotFound = (error: unknown) => isApiError(error) && error.status === 404

// --- hooks -----------------------------------------------------------------------------------------

export function useConversations(filters: ConversationFilters = {}, { poll = true, enabled = true } = {}) {
  return useQuery({
    queryKey: messagingKeys.conversations(filters),
    queryFn: () => getConversations(filters),
    placeholderData: keepPreviousData,
    refetchInterval: poll ? 15_000 : false,
    enabled,
  })
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: messagingKeys.conversation(id ?? ''),
    queryFn: () => getConversation(id as string),
    enabled: Boolean(id),
  })
}

export function useMessages(id: string | null) {
  return useQuery({
    queryKey: messagingKeys.messages(id ?? ''),
    queryFn: () => getMessages(id as string),
    enabled: Boolean(id),
    refetchInterval: 8_000,
  })
}

export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: messagingKeys.unread,
    queryFn: getUnreadCount,
    refetchInterval: 60_000,
    enabled,
  })
}

export function useTemplates() {
  return useQuery({ queryKey: messagingKeys.templates, queryFn: getTemplates })
}

export function useVariables() {
  return useQuery({ queryKey: messagingKeys.variables, queryFn: getVariables, staleTime: Infinity })
}

export function useRules() {
  return useQuery({ queryKey: messagingKeys.rules, queryFn: getRules })
}

export function useRecipient(params: RecipientParams, enabled = true) {
  return useQuery({ queryKey: messagingKeys.recipient(params), queryFn: () => getRecipient(params), enabled })
}

/** Team members a conversation can be assigned to (the list needs `accounts.users_manage`). */
export function useTeamMembers(enabled: boolean) {
  return useQuery({
    queryKey: ['messaging', 'members'],
    queryFn: () => api.get<Page<Member>>('/accounts/users/', { params: { page_size: 200 } }),
    enabled,
    staleTime: 5 * 60_000,
  })
}

/** Mutation that refreshes every messaging query when it succeeds. */
export function useMessagingMutation<TVariables, TData>(
  fn: (variables: TVariables) => Promise<TData>,
  options: { onSuccess?: (data: TData, variables: TVariables) => void } = {},
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (data, variables) => {
      options.onSuccess?.(data, variables)
      await queryClient.invalidateQueries({ queryKey: messagingKeys.all })
    },
  })
}
