/**
 * Compliance API client (backend `apps/compliance`, docs/integration-notes/C7-compliance.md): DIAN electronic
 * invoices, SIRE files (Migración Colombia) and TRA registrations (MinCIT). Money is a decimal string.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type Money = string
export type InvoiceKind = 'invoice' | 'credit_note'
export type InvoiceStatus = 'draft' | 'issued' | 'accepted' | 'rejected' | 'cancelled' | 'error'
export type IntegrationMode = 'real' | 'simulated'
export type Environment = 'test' | 'production'
export type TaxStatus = 'taxed' | 'exempt' | 'excluded'
export type SireStatus = 'generated' | 'submitted' | 'acknowledged'
export type TraStatus = 'pending' | 'registered' | 'error'
export type Movement = 'E' | 'S'
export type HealthStatus = 'ok' | 'warning' | 'critical' | 'missing'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---------------------------------------------------------------------------------------------- invoices

export interface InvoiceSummary {
  id: string
  kind: InvoiceKind
  status: InvoiceStatus
  /** Full number with prefix ("SETT128"); empty for drafts without number. */
  number: string
  prefix: string
  issue_date: string
  issued_at: string | null
  currency: string
  subtotal: Money
  tax_total: Money
  total: Money
  customer_name: string
  customer_document: string
  reservation_id: string | null
  reservation_code: string
  related_invoice_id: string | null
  related_number: string
  mode: IntegrationMode
  environment: Environment
  attempts: number
  error_message: string
  has_pdf: boolean
  is_exempt: boolean
  created_at: string
  /** P4: invoices to a company with credit ("a crédito") fall due this day. */
  due_date?: string | null
  /** P4: invoiced to a company's NIT (company folio). */
  is_company?: boolean
}

export interface InvoiceCustomer {
  guest_id: string | null
  name: string
  document_type: string
  dian_document_code: string
  document_number: string
  dv: string
  legal_organization: 'person' | 'company'
  is_final_consumer: boolean
  is_foreign_non_resident: boolean
  email: string
  phone: string
  address: string
  city: string
  country: string
  nationality: string
  /** P4 (company customers): the company, its trade name, VAT regime, DIAN responsibilities and payment terms. */
  company_id?: string
  trade_name?: string
  vat_responsible?: boolean
  tax_responsibilities?: string[]
  payment_form?: 'cash' | 'credit'
  payment_terms_days?: number
}

export interface InvoiceLine {
  code: string
  kind: string
  description: string
  quantity: number
  unit_price: Money
  net: Money
  tax_code: string
  tax_status: TaxStatus
  tax_rate: string
  tax_amount: Money
  total: Money
}

export interface InvoiceDetail extends InvoiceSummary {
  customer: InvoiceCustomer
  lines: InvoiceLine[]
  exempt_note: string
  cufe: string
  qr_data: string
  validation_url: string
  provider: string
  provider_ref: string
  reason: string
  credit_notes: { id: string; number: string; status: InvoiceStatus; issue_date: string; reason: string }[]
  resolution: {
    id: string
    prefix: string
    resolution_number: string
    from_number: number
    to_number: number
    valid_from: string
    valid_to: string
  } | null
  folio_id: string
  charges_count: number
  last_attempt_at: string | null
}

export interface InvoiceTotals {
  start: string
  end: string
  invoices: number
  total: Money
  subtotal: Money
  tax_total: Money
  exempt: { count: number; total: Money }
  credit_notes: number
  failed: number
  waiting_dian: number
}

export interface InvoiceFilters {
  status?: InvoiceStatus
  kind?: InvoiceKind
  start?: string
  end?: string
  q?: string
  page?: number
  page_size?: number
}

// ------------------------------------------------------------------------------------------- resolutions

export interface Resolution {
  id: string
  document_kind: InvoiceKind
  prefix: string
  resolution_number: string
  from_number: number
  to_number: number
  current_number: number
  next_number: number
  remaining: number
  valid_from: string
  valid_to: string
  technical_key: string
  environment: Environment
  provider_range_id: string
  is_active: boolean
  invoices_count: number
  created_at: string
  updated_at: string
}

export type ResolutionInput = Pick<
  Resolution,
  | 'document_kind'
  | 'prefix'
  | 'resolution_number'
  | 'from_number'
  | 'to_number'
  | 'valid_from'
  | 'valid_to'
  | 'technical_key'
  | 'environment'
  | 'provider_range_id'
  | 'is_active'
>

export interface ResolutionHealth {
  status: HealthStatus
  message: string
  resolution_id?: string
  prefix?: string
  from_number?: number
  to_number?: number
  next_number?: number
  remaining?: number
  used_percent?: number
  valid_to?: string
  days_left?: number
  environment?: Environment
}

// -------------------------------------------------------------------------------------------------- SIRE

export interface SireReport {
  id: string
  period_start: string
  /** Inclusive. */
  period_end: string
  status: SireStatus
  records_count: number
  missing_count: number
  mode: IntegrationMode
  generated_at: string
  generated_by_name: string | null
  submitted_at: string | null
  submitted_by_name: string | null
  ack_code: string
  file_name: string
}

export interface SireMissing {
  guest_id: string
  guest_name: string
  reservation_id: string
  reservation_code: string
  stay_id: string
  movement: Movement
  movement_date: string
  fields: string[]
  /** False when the guest has no nationality (not even a row could be built). */
  record: boolean
}

export interface SireRecordRow {
  id: string
  guest_id: string
  guest_name: string
  reservation_id: string
  reservation_code: string
  movement: Movement
  movement_date: string
  complete: boolean
  missing_fields: string[]
  document: string
  nationality: string
}

export interface SireReportDetail extends SireReport {
  missing: SireMissing[]
  records: SireRecordRow[]
}

// --------------------------------------------------------------------------------------------------- TRA

export interface TraRegistration {
  id: string
  status: TraStatus
  tra_number: string
  guest: { id: string; full_name: string; document_type: string; document_number: string; nationality: string }
  reservation_id: string
  reservation_code: string
  stay_id: string
  room: string
  checkin_date: string
  checkout_date: string
  is_main: boolean
  parent_id: string | null
  mode: IntegrationMode
  missing_fields: string[]
  error: string
  attempts: number
  registered_at: string | null
  last_attempt_at: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface TraFilters {
  status?: TraStatus
  date?: string
  q?: string
  reservation?: string
  page?: number
  page_size?: number
}

// ------------------------------------------------------------------------------------------------ pending

export interface PendingInvoice {
  status: 'not_issued' | InvoiceStatus
  invoice_id: string | null
  number: string
  kind: InvoiceKind
  reservation_id: string | null
  reservation_code: string
  guest_name: string
  checkout_date: string | null
  total: Money
  error: string
}

export interface PendingTra {
  status: 'not_registered' | TraStatus
  registration_id: string | null
  reservation_id: string
  reservation_code: string
  stay_id: string
  guest_id: string | null
  guest_name: string
  room: string
  checkin_date: string
  missing_fields: string[]
  error: string
}

export interface PendingSummary {
  resolution: ResolutionHealth
  invoices: { count: number; items: PendingInvoice[] }
  tra: { count: number; items: PendingTra[] }
  sire: {
    count: number
    reports: {
      report_id: string
      period_start: string
      period_end: string
      records_count: number
      missing_count: number
      generated_at: string
    }[]
    missing: SireMissing[]
    unreported_days: string[]
  }
  counts: { invoices: number; tra: number; sire: number; total: number }
}

export interface PendingCounts {
  counts: PendingSummary['counts']
  resolution_status: HealthStatus
}

// --------------------------------------------------------------------------------------------- settings

export interface ComplianceSettings {
  go_live_date: string | null
  auto_issue_invoices: boolean
  final_consumer_id: string
  invoice_notes: string
  sire_establishment_code: string
  sire_city_code: string
  sire_document_codes: Record<string, string>
  sire_country_codes: Record<string, string>
  sire_second_surname_column: boolean
  tra_auto_register: boolean
  tra_establishment_id: string
  tra_travel_reason: string
  tra_accommodation_type: string
}

export interface ComplianceSettingsPayload extends ComplianceSettings {
  effective: { sire_city_code: string; tra_establishment_id: string; tra_accommodation_type: string }
  defaults: {
    sire_document_codes: Record<string, string>
    sire_country_codes: Record<string, string>
    travel_reasons: Record<string, string>
  }
  integrations: Record<
    'einvoice' | 'sire' | 'tra',
    { mode: IntegrationMode; enabled: boolean; status: string; provider_label: string }
  >
  supplier: { legal_name: string; nit: string; rnt: string; city: string; missing: string[] }
}

// ------------------------------------------------------------------------------------ reservation "Legal"

export interface InvoicePreview {
  customer: InvoiceCustomer
  lines: InvoiceLine[]
  subtotal: Money
  tax_total: Money
  total: Money
  exempt_note: string
  charges_count: number
}

export interface ReservationLegal {
  reservation: {
    id: string
    code: string
    status: string
    checkout_date: string
    booker: {
      id: string
      full_name: string
      document_type: string
      document_number: string
      nationality: string
      is_foreign_non_resident: boolean
    }
  }
  invoices: InvoiceSummary[]
  uninvoiced: { count: number; total: Money }
  can_issue: boolean
  has_accepted_invoice: boolean
  tra: TraRegistration[]
  tra_candidates: { stay_id: string; status: string; room: string; checkin_date: string; guests: string[] }[]
  sire: {
    id: string
    report_id: string
    report_status: SireStatus
    guest_id: string
    guest_name: string
    movement: Movement
    movement_date: string
    complete: boolean
    missing_fields: string[]
  }[]
  warnings: ('final_consumer' | 'invoice_failed' | 'tra_pending' | 'sire_missing')[]
  resolution: ResolutionHealth
  preview: InvoicePreview | null
  /** P4 ("Facturar a"): one row per customer — the guest side and each company folio — with what is pending. */
  folios?: LegalFolio[]
}

export interface LegalFolio {
  /** Issue this row with `POST invoices/issue/ {folio_id}`. */
  folio_id: string
  folio_ids: string[]
  folio_type: 'guest' | 'company'
  status: 'open' | 'closed'
  company_id: string | null
  customer: InvoiceCustomer
  uninvoiced: { count: number; total: Money }
  can_issue: boolean
  preview: InvoicePreview | null
}

// ------------------------------------------------------------------------------------------ query keys

export const complianceKeys = {
  all: ['compliance'] as const,
  invoices: (filters: InvoiceFilters) => ['compliance', 'invoices', filters] as const,
  invoice: (id: string) => ['compliance', 'invoice', id] as const,
  invoiceTotals: (start?: string, end?: string) => ['compliance', 'invoice-totals', start, end] as const,
  resolutions: ['compliance', 'resolutions'] as const,
  sireReports: ['compliance', 'sire'] as const,
  sireReport: (id: string) => ['compliance', 'sire-report', id] as const,
  tra: (filters: TraFilters) => ['compliance', 'tra', filters] as const,
  pending: ['compliance', 'pending'] as const,
  pendingCounts: ['compliance', 'pending-counts'] as const,
  settings: ['compliance', 'settings'] as const,
  legal: (reservationId: string) => ['compliance', 'legal', reservationId] as const,
}

const BASE = '/compliance'

// ----------------------------------------------------------------------------------------------- queries

export function useInvoices(filters: InvoiceFilters) {
  return useQuery({
    queryKey: complianceKeys.invoices(filters),
    queryFn: ({ signal }) => api.get<Page<InvoiceSummary>>(`${BASE}/invoices/`, { params: { ...filters }, signal }),
    placeholderData: keepPreviousData,
  })
}

export function useInvoice(id: string | null) {
  return useQuery({
    queryKey: complianceKeys.invoice(id ?? ''),
    queryFn: ({ signal }) => api.get<InvoiceDetail>(`${BASE}/invoices/${id}/`, { signal }),
    enabled: Boolean(id),
  })
}

export function useInvoiceTotals(start?: string, end?: string) {
  return useQuery({
    queryKey: complianceKeys.invoiceTotals(start, end),
    queryFn: ({ signal }) => api.get<InvoiceTotals>(`${BASE}/invoices/summary/`, { params: { start, end }, signal }),
  })
}

export function useResolutions() {
  return useQuery({
    queryKey: complianceKeys.resolutions,
    queryFn: ({ signal }) => api.get<Resolution[] | Page<Resolution>>(`${BASE}/resolutions/`, { signal }),
    select: (data) => (Array.isArray(data) ? data : data.results),
  })
}

export function useSireReports() {
  return useQuery({
    queryKey: complianceKeys.sireReports,
    queryFn: ({ signal }) =>
      api.get<Page<SireReport>>(`${BASE}/sire/`, { params: { page_size: 100 }, signal }),
  })
}

export function useSireReport(id: string | null) {
  return useQuery({
    queryKey: complianceKeys.sireReport(id ?? ''),
    queryFn: ({ signal }) => api.get<SireReportDetail>(`${BASE}/sire/${id}/`, { signal }),
    enabled: Boolean(id),
  })
}

export function useTraRegistrations(filters: TraFilters) {
  return useQuery({
    queryKey: complianceKeys.tra(filters),
    queryFn: ({ signal }) => api.get<Page<TraRegistration>>(`${BASE}/tra/`, { params: { ...filters }, signal }),
    placeholderData: keepPreviousData,
  })
}

export function usePending() {
  return useQuery({
    queryKey: complianceKeys.pending,
    queryFn: ({ signal }) => api.get<PendingSummary>(`${BASE}/pending/`, { signal }),
  })
}

export function usePendingCounts() {
  return useQuery({
    queryKey: complianceKeys.pendingCounts,
    queryFn: ({ signal }) => api.get<PendingCounts>(`${BASE}/pending/`, { params: { summary: 1 }, signal }),
  })
}

export function useComplianceSettings() {
  return useQuery({
    queryKey: complianceKeys.settings,
    queryFn: ({ signal }) => api.get<ComplianceSettingsPayload>(`${BASE}/settings/`, { signal }),
  })
}

export function useReservationLegal(reservationId: string) {
  return useQuery({
    queryKey: complianceKeys.legal(reservationId),
    queryFn: ({ signal }) => api.get<ReservationLegal>(`${BASE}/reservations/${reservationId}/`, { signal }),
  })
}

// --------------------------------------------------------------------------------------------- mutations

/** Every compliance mutation refreshes all compliance data (lists, counts, the reservation's Legal tab). */
function useComplianceMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: complianceKeys.all }),
  })
}

export const useIssueInvoice = () =>
  useComplianceMutation((body: { reservation_id: string } | { folio_id: string }) =>
    api.post<InvoiceDetail>(`${BASE}/invoices/issue/`, body),
  )

export const useRetryInvoice = () =>
  useComplianceMutation((id: string) => api.post<InvoiceDetail>(`${BASE}/invoices/${id}/retry/`))

export const useCreditNote = () =>
  useComplianceMutation(({ id, reason }: { id: string; reason: string }) =>
    api.post<InvoiceDetail>(`${BASE}/invoices/${id}/credit-note/`, { reason, confirm: true }),
  )

export const useGenerateSire = () =>
  useComplianceMutation((body: { start: string; end: string }) =>
    api.post<SireReportDetail>(`${BASE}/sire/generate/`, body),
  )

export const useMarkSireSubmitted = () =>
  useComplianceMutation(({ id, ack_code }: { id: string; ack_code?: string }) =>
    api.post<SireReportDetail>(`${BASE}/sire/${id}/mark-submitted/`, { ack_code: ack_code ?? '' }),
  )

export const useRetryTra = () =>
  useComplianceMutation((id: string) => api.post<TraRegistration>(`${BASE}/tra/${id}/retry/`))

export const useRegisterTra = () =>
  useComplianceMutation((stayId: string) =>
    api.post<TraRegistration[]>(`${BASE}/tra/register/`, { stay_id: stayId }),
  )

export const useSaveSettings = () =>
  useComplianceMutation((body: Partial<ComplianceSettings>) =>
    api.patch<ComplianceSettingsPayload>(`${BASE}/settings/`, body),
  )

export const useSaveResolution = () =>
  useComplianceMutation(({ id, ...body }: Partial<ResolutionInput> & { id?: string }) =>
    id ? api.patch<Resolution>(`${BASE}/resolutions/${id}/`, body) : api.post<Resolution>(`${BASE}/resolutions/`, body),
  )

export const useDeleteResolution = () =>
  useComplianceMutation((id: string) => api.delete<void>(`${BASE}/resolutions/${id}/`))

// ------------------------------------------------------------------------------------------------- files

export function fetchInvoiceFile(id: string, format: 'pdf' | 'xml'): Promise<Blob> {
  return api.get<Blob>(`${BASE}/invoices/${id}/${format}/`, { responseType: 'blob' })
}

export function fetchSireFile(id: string): Promise<Blob> {
  return api.get<Blob>(`${BASE}/sire/${id}/download/`, { responseType: 'blob' })
}
