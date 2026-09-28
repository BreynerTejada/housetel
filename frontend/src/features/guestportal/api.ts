import { useQuery } from '@tanstack/react-query'
import { api, publicApi } from '@/lib/api'

/**
 * Guest portal API (backend `apps/guestportal`, notes in docs/integration-notes/C5-guestportal.md).
 * Public: `/api/v1/public/guestportal/<token>/…` (the signed token is the key, no session).
 * Staff: `/api/v1/guestportal/…` (session + X-Property-Id).
 */

export type Money = string
export type I18nText = Record<string, string>
export type ReservationStatus = 'tentative' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show'
export type CheckinStatus = 'not_started' | 'in_progress' | 'completed'
export type CheckinStep = 'guests' | 'documents' | 'arrival' | 'signature' | 'payment' | 'done'
export type WindowReason = 'not_open_yet' | 'tentative' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show' | 'past'
export type RequestKind = 'late_checkout' | 'early_checkin' | 'transfer' | 'extra' | 'other'
export type RequestStatus = 'requested' | 'approved' | 'rejected' | 'done'
export type ChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'
export type DocumentKind = 'id_front' | 'id_back' | 'passport' | 'other'
export type MissingCode = 'guest_data' | 'document' | 'signature' | 'terms'

// ---- Public payloads ------------------------------------------------------------------------------

export interface PortalProperty {
  name: string
  slug: string
  city: string
  address: string
  phone: string
  email: string
  website: string
  check_in_time: string | null
  check_out_time: string | null
  timezone: string
  currency: string
  default_language: string
  primary_color: string
  logo: string
  photo: string | null
  house_rules: I18nText
}

export interface PortalReservation {
  code: string
  status: ReservationStatus
  source: string
  channel_code: string
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  currency: string
  total_amount: Money
  eta: string | null
  language: string
  cancelled_at: string | null
  cancellation_fee: Money
}

export interface PortalStay {
  id: string
  status: ReservationStatus
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  room_type: { id: string; code: string; name: I18nText; kind: 'private' | 'dorm'; photo: string | null }
  rate_plan: { id: string; code: string; name: I18nText; meal_plan: string }
  room: { number: string } | null
  total_amount: Money
}

export interface PortalGuest {
  id: string
  first_name: string
  full_name: string
  role: 'booker' | 'occupant'
  stay_id: string | null
}

export interface PortalBalance {
  total: Money
  paid: Money
  due: Money
  currency: string
  can_pay: boolean
}

export interface CheckinWindow {
  opens_on: string
  is_open: boolean
  reason: WindowReason | null
}

export interface PortalCheckinSummary extends CheckinWindow {
  status: CheckinStatus
  current_step: CheckinStep
  completed_at: string | null
}

export interface PortalExtra {
  id: string
  code: string
  name: I18nText
  charge_type: ChargeType
  unit_price: Money
  default_quantity: number
  default_total: Money
  tax_exempt: boolean
  currency: string
}

export interface ServiceRequest {
  id: string
  kind: RequestKind
  status: RequestStatus
  extra: { id: string; code: string; name: I18nText } | null
  quantity: number
  requested_time: string | null
  notes: string
  price: Money | null
  decision_note: string
  created_at: string
  decided_at: string | null
}

export interface CancellationInfo {
  can_cancel: boolean
  reason: 'disabled' | 'channel' | 'status' | 'past' | null
  fee: Money
  fee_reason: string
  free_until: string | null
  non_refundable: boolean
  policy: { name: I18nText; description: I18nText }
  currency: string
}

export interface ModificationInfo {
  can_modify: boolean
  reason: 'disabled' | 'channel' | 'status' | 'multiple_rooms' | 'past' | 'non_refundable' | 'outside_free_window' | null
  free_until: string | null
  max_nights: number
}

export interface PortalPayment {
  date: string
  method: string
  amount: Money
}

/** A message of the booking's thread (C6): `in` = written by the guest, `out` = by the hotel. */
export interface PortalMessage {
  id: string
  direction: 'in' | 'out'
  channel: 'email' | 'whatsapp' | 'web_chat' | 'ota' | string
  subject: string
  body: string
  created_at: string
}

export interface PortalSummary {
  today: string
  property: PortalProperty
  reservation: PortalReservation
  stays: PortalStay[]
  guests: PortalGuest[]
  balance: PortalBalance
  payments: PortalPayment[]
  checkin: PortalCheckinSummary
  extras: PortalExtra[]
  requests: ServiceRequest[]
  messages?: PortalMessage[]
  cancellation: CancellationInfo
  modification: ModificationInfo
  settings: { auto_approve_extras: boolean }
}

export interface SlotDocument {
  id: string
  kind: DocumentKind | 'signature'
  uploaded_via: 'staff' | 'portal'
  created_at: string
}

/** What the portal shows of a guest: the booker's own profile, or only name + masked document of a companion. */
export interface SlotData {
  first_name?: string
  last_name?: string
  document_type?: string
  document_number?: string
  document_hint?: string
  nationality?: string
  country_of_residence?: string
  city_of_residence?: string
  birth_date?: string | null
  email?: string
  phone?: string
}

export interface TravelData {
  travel_reason?: string
  origin?: string
  destination?: string
}

export interface CheckinSlot {
  slot: number
  stay_id: string
  role: 'booker' | 'companion'
  guest_id: string | null
  complete: boolean
  is_adult: boolean
  /** `child`: a registered minor, or an empty slot the booking holds for a child. */
  expected?: 'adult' | 'child'
  data: SlotData
  travel: TravelData
  documents: SlotDocument[]
}

export interface MissingItem {
  code: MissingCode
  slot?: number
  stay_id?: string
  guest_id?: string | null
}

export interface CheckinPayload {
  status: CheckinStatus
  current_step: CheckinStep
  completed_at: string | null
  window: CheckinWindow
  settings: { require_document_photo: boolean; require_signature: boolean }
  terms: I18nText
  travel_reasons: string[]
  property: PortalProperty
  reservation: PortalReservation
  stays: PortalStay[]
  guests: CheckinSlot[]
  eta: string | null
  signature: { signed: boolean; accepted_terms_at: string | null }
  missing: MissingItem[]
  balance: PortalBalance
}

export interface GuestEntry {
  stay_id: string
  role: 'booker' | 'companion'
  guest_id?: string | null
  keep?: boolean
  first_name?: string
  last_name?: string
  document_type?: string
  document_number?: string
  nationality?: string
  country_of_residence?: string
  city_of_residence?: string
  birth_date?: string | null
  email?: string
  phone?: string
  travel_reason?: string
  origin?: string
  destination?: string
}

export interface PaymentLink {
  reference: string
  checkout_url: string
  amount: Money
  currency: string
  status: string
  mode: string
  expires_at: string | null
}

export interface ModificationPreview {
  checkin: string
  checkout: string
  nights: number
  current_total: Money
  total: Money
  difference: Money
  balance: Money
  currency: string
}

/** C7's invoices for the portal (`/public/compliance/portal/<token>/invoices/`); 404 until C7 exists. */
export interface PortalInvoice {
  id: string
  number: string
  kind: 'invoice' | 'credit_note' | string
  status: string
  total: Money
  issued_at: string | null
  pdf_url?: string | null
}

export interface NewRequest {
  kind: RequestKind
  extra_id?: string
  quantity?: number
  requested_time?: string | null
  notes?: string
}

// ---- Public calls ---------------------------------------------------------------------------------

const portalPath = (token: string, path = '') => `/guestportal/${encodeURIComponent(token)}/${path}`

export const getPortal = (token: string) => publicApi.get<PortalSummary>(portalPath(token))
export const getCheckin = (token: string) => publicApi.get<CheckinPayload>(portalPath(token, 'checkin/'))

export const saveGuests = (token: string, guests: GuestEntry[]) =>
  publicApi.post<CheckinPayload>(portalPath(token, 'checkin/'), { step: 'guests', guests })

export function uploadDocument(token: string, { guestId, kind, file }: { guestId: string; kind: DocumentKind; file: File }) {
  const formData = new FormData()
  formData.append('step', 'documents')
  formData.append('guest_id', guestId)
  formData.append('kind', kind)
  formData.append('file', file)
  return publicApi.post<{ document: { id: string; kind: DocumentKind; guest_id: string }; checkin: CheckinPayload }>(
    portalPath(token, 'checkin/'),
    undefined,
    { formData },
  )
}

export const confirmDocuments = (token: string) =>
  publicApi.post<CheckinPayload>(portalPath(token, 'checkin/'), { step: 'documents' })

export const saveArrival = (token: string, eta: string | null) =>
  publicApi.post<CheckinPayload>(portalPath(token, 'checkin/'), { step: 'arrival', eta })

export const saveSignature = (
  token: string,
  body: { signature: string; accept_terms: boolean; marketing_consent: boolean },
) => publicApi.post<CheckinPayload>(portalPath(token, 'checkin/'), { step: 'signature', ...body })

export const completeCheckin = (token: string) => publicApi.post<CheckinPayload>(portalPath(token, 'checkin/complete/'))

export const payBalance = (token: string, amount?: Money) =>
  publicApi.post<PaymentLink>(portalPath(token, 'pay/'), amount ? { amount } : {})

export const createRequest = (token: string, body: NewRequest) =>
  publicApi.post<PortalSummary & { request: ServiceRequest }>(portalPath(token, 'requests/'), body)

export const cancelBooking = (token: string, reason: string) =>
  publicApi.post<PortalSummary>(portalPath(token, 'cancel/'), { confirm: true, reason })

export const previewModification = (token: string, checkin: string, checkout: string) =>
  publicApi.post<ModificationPreview>(portalPath(token, 'modify-preview/'), { checkin, checkout })

export const modifyBooking = (token: string, checkin: string, checkout: string) =>
  publicApi.post<{ total: Money; balance: Money; currency: string; summary: PortalSummary }>(
    portalPath(token, 'modify/'),
    { checkin, checkout },
  )

export const getInvoices = (token: string) =>
  publicApi.get<PortalInvoice[] | { results: PortalInvoice[] }>(`/compliance/portal/${encodeURIComponent(token)}/invoices/`)

/** Where the guest downloads an invoice: the URL C7 gives, or its documented path. */
export function invoicePdfUrl(token: string, invoice: PortalInvoice): string {
  return invoice.pdf_url || `/api/v1/public/compliance/portal/${encodeURIComponent(token)}/invoices/${invoice.id}/pdf/`
}

// ---- Staff payloads -------------------------------------------------------------------------------

export interface StaffDocument extends SlotDocument {
  file_url: string
}

export interface StaffSlot extends Omit<CheckinSlot, 'data' | 'documents'> {
  data: Required<Omit<SlotData, 'document_hint'>> & { full_name: string; is_foreign_non_resident: boolean } | Record<string, never>
  documents: StaffDocument[]
}

export interface StaffCheckin {
  reservation_id: string
  code: string
  status: CheckinStatus
  current_step: CheckinStep
  completed_at: string | null
  accepted_terms_at: string | null
  eta: string | null
  ip: string | null
  user_agent: string
  signature_url: string | null
  window: CheckinWindow
  guests: StaffSlot[]
  missing: MissingItem[]
  requests: ServiceRequest[]
  portal_url: string
  checkin_url: string
}

export interface ArrivalCheckin {
  reservation_id: string
  code: string
  status: ReservationStatus
  guest_name: string
  is_vip: boolean
  adults: number
  children: number
  checkin_status: CheckinStatus
  completed_at: string | null
  eta: string | null
}

export interface PortalLink {
  url: string
  checkin_url: string
  qr_png: string
}

export interface SendLinkResult {
  url: string
  checkin_url: string
  messages: { channel: string; to: string; status: string; error: string }[]
  send_error?: string
}

export interface StaffServiceRequest extends ServiceRequest {
  reservation: {
    id: string
    code: string
    guest_name: string
    checkin_date: string
    checkout_date: string
    status: ReservationStatus
  }
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface PortalSettings {
  checkin_opens_days_before: number
  require_document_photo: boolean
  require_signature: boolean
  auto_approve_extras: boolean
  allow_guest_cancellation: boolean
  allow_guest_modification: boolean
  terms: { es: string; en: string }
  updated_at: string
}

export interface CatalogExtra {
  id: string
  code: string
  name: I18nText
  price: Money
  charge_type: ChargeType
  is_active: boolean
}

// ---- Staff calls ----------------------------------------------------------------------------------

export const getReservationCheckin = (reservationId: string) =>
  api.get<StaffCheckin>(`/guestportal/reservations/${reservationId}/checkin/`)

export const getPortalLink = (reservationId: string) => api.get<PortalLink>(`/guestportal/reservations/${reservationId}/link/`)

export const sendCheckinLink = (reservationId: string, sendVia: ('email' | 'whatsapp')[]) =>
  api.post<SendLinkResult>(`/guestportal/reservations/${reservationId}/send-link/`, { send_via: sendVia })

export const getArrivalsCheckins = (date?: string) => api.get<ArrivalCheckin[]>('/guestportal/checkins/', { params: { date } })

export const getServiceRequests = (params: { status?: RequestStatus[]; reservation?: string; page_size?: number }) =>
  api.get<Page<StaffServiceRequest>>('/guestportal/service-requests/', { params: { ...params, status: params.status } })

export const approveRequest = (id: string, body: { extra_id?: string; quantity?: number; note?: string }) =>
  api.post<StaffServiceRequest>(`/guestportal/service-requests/${id}/approve/`, body)

export const rejectRequest = (id: string, reason: string) =>
  api.post<StaffServiceRequest>(`/guestportal/service-requests/${id}/reject/`, { reason })

export const completeRequest = (id: string) => api.post<StaffServiceRequest>(`/guestportal/service-requests/${id}/complete/`)

export const getPortalSettings = () => api.get<PortalSettings>('/guestportal/settings/')

export const updatePortalSettings = (patch: Partial<Omit<PortalSettings, 'updated_at'>>) =>
  api.patch<PortalSettings>('/guestportal/settings/', patch)

export const getCatalogExtras = () =>
  api.get<Page<CatalogExtra>>('/rates/extras/', { params: { is_active: true, page_size: 200 } })

// ---- Query keys and hooks -------------------------------------------------------------------------

export const portalKeys = {
  all: ['guestportal'] as const,
  portal: (token: string) => ['guestportal', 'portal', token] as const,
  checkin: (token: string) => ['guestportal', 'checkin', token] as const,
  invoices: (token: string) => ['guestportal', 'invoices', token] as const,
  staff: ['guestportal', 'staff'] as const,
  reservationCheckin: (id: string) => ['guestportal', 'staff', 'checkin', id] as const,
  link: (id: string) => ['guestportal', 'staff', 'link', id] as const,
  arrivals: (date?: string) => ['guestportal', 'staff', 'arrivals', date ?? 'today'] as const,
  requests: (filters: Record<string, unknown>) => ['guestportal', 'staff', 'requests', filters] as const,
  settings: ['guestportal', 'staff', 'settings'] as const,
  extras: ['guestportal', 'staff', 'catalog-extras'] as const,
}

export function usePortal(token: string) {
  return useQuery({ queryKey: portalKeys.portal(token), queryFn: () => getPortal(token), retry: false })
}

export function useCheckin(token: string) {
  return useQuery({ queryKey: portalKeys.checkin(token), queryFn: () => getCheckin(token), retry: false })
}

/** C7's invoices, or an empty list when the endpoint is missing (404) or fails: the section just hides. */
export function useInvoices(token: string, enabled = true) {
  return useQuery({
    queryKey: portalKeys.invoices(token),
    queryFn: async () => {
      try {
        const data = await getInvoices(token)
        return Array.isArray(data) ? data : (data?.results ?? [])
      } catch {
        return [] as PortalInvoice[]
      }
    },
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
  })
}
