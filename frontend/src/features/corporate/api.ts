/**
 * Corporate API client (backend `apps/corporate`, docs/integration-notes/P4-corporate-billing.md): companies,
 * the billing of a reservation (who pays what), account statements, receivables and payments on account.
 * Money is always a decimal string ("350000.00").
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { complianceKeys } from '@/features/compliance/api'
import { financeKeys } from '@/features/finance/api'

export type Money = string
export type CompanyKind = 'corporate' | 'travel_agency' | 'government' | 'other'
export type BillTo = 'guest' | 'company'
export type Route = 'lodging' | 'lodging_taxes' | 'extras' | 'all'
export type AgingKey = 'current' | 'd31_60' | 'd61_90' | 'd90_plus'
export type Aging = Record<AgingKey, Money>
export type ArMethod = 'bank_transfer' | 'cash' | 'card_terminal' | 'other'

export const COMPANY_KINDS: CompanyKind[] = ['corporate', 'travel_agency', 'government', 'other']
export const ROUTES: Route[] = ['lodging', 'lodging_taxes', 'extras', 'all']
export const AGING_KEYS: AgingKey[] = ['current', 'd31_60', 'd61_90', 'd90_plus']
export const AR_METHODS: ArMethod[] = ['bank_transfer', 'cash', 'card_terminal', 'other']
/** DIAN fiscal responsibilities (anexo técnico, tabla 13.2.6.1). */
export const TAX_RESPONSIBILITIES = ['O-13', 'O-15', 'O-23', 'O-47', 'R-99-PN'] as const

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface CompanyContact {
  name: string
  role: string
  email: string
  phone: string
}

export interface CreditStatus {
  enabled: boolean
  /** null = no limit. */
  limit: Money | null
  /** Open company folios + lodging still to post of its stays in progress − credit in favor (whole organization). */
  used: Money
  available: Money | null
  over_limit: boolean
  terms_days: number
}

export interface CompanyRef {
  id: string
  legal_name: string
  trade_name: string
  kind: CompanyKind
  nit: string
  dv: string
  nit_display: string
  credit_enabled: boolean
  payment_terms_days: number
  is_active: boolean
}

export interface Company {
  id: string
  kind: CompanyKind
  legal_name: string
  trade_name: string
  nit: string
  dv: string
  nit_display: string
  vat_responsible: boolean
  tax_responsibilities: string[]
  address: string
  city: string
  department: string
  country: string
  billing_email: string
  phone: string
  credit_enabled: boolean
  credit_limit: Money | null
  payment_terms_days: number
  contacts: CompanyContact[]
  notes: string
  is_active: boolean
  /** At the active property. */
  receivable: { balance: Money; overdue: Money; in_progress: Money } | null
  created_at: string
  updated_at: string
  /** Only in the detail. */
  credit?: CreditStatus
}

export type CompanyInput = Omit<Company, 'id' | 'nit_display' | 'receivable' | 'created_at' | 'updated_at' | 'credit'>

export interface CompanyFilters {
  q?: string
  kind?: CompanyKind
  active?: boolean
  with_balance?: boolean
  page?: number
  page_size?: number
}

export interface StatementItem {
  folio_id: string
  folio_status: 'open' | 'closed'
  kind: 'reservation' | 'opening_balance'
  label: string
  reservation: {
    id: string
    code: string
    status: string
    checkin_date: string
    checkout_date: string
    guest_name: string
  } | null
  invoice: { id: string; number: string; status: string; issue_date: string; total: Money } | null
  document_date: string | null
  due_date: string | null
  age_days: number
  overdue_days: number
  bucket: AgingKey
  charges_total: Money
  paid: Money
  balance: Money
  expected_balance: Money
}

export interface AccountPaymentRow {
  id: string
  amount: Money
  applied: Money
  unapplied: Money
  method: ArMethod
  reference: string
  received_on: string
  notes: string
  status: 'active' | 'voided'
  created_by: string | null
  created_at: string
  voided_at: string | null
  void_reason: string
  allocations: { id: string; folio_id: string; amount: Money; label: string; reservation_code: string | null }[]
}

export interface StatementTotals {
  balance: Money
  overdue: Money
  in_progress: Money
  unapplied: Money
  net_balance: Money
  open_items: number
}

export interface Statement {
  company: CompanyRef
  as_of: string
  currency: string
  totals: StatementTotals
  aging: Aging
  credit: CreditStatus
  items: StatementItem[]
  in_progress: StatementItem[]
  payments: AccountPaymentRow[]
}

export interface ReceivablesRow {
  company: CompanyRef
  balance: Money
  overdue: Money
  in_progress: Money
  unapplied: Money
  net_balance: Money
  aging: Aging
  open_items: number
  oldest_days: number
}

export interface Receivables {
  as_of: string
  currency: string
  totals: { balance: Money; overdue: Money; in_progress: Money; unapplied: Money; net_balance: Money; companies: number }
  aging: Aging
  companies: ReceivablesRow[]
}

export interface CompanyReservation {
  id: string
  code: string
  status: string
  checkin_date: string
  checkout_date: string
  guest_name: string
  billed_to_company: boolean
  routing: Route[]
  purchase_order: string
  company_balance: Money
  invoice_number: string
}

export interface BillingFolio {
  id: string
  folio_type: 'guest' | 'master' | 'house' | 'company'
  status: 'open' | 'closed'
  company: CompanyRef | null
  balance: Money
  expected_balance: Money
}

export interface ReservationBilling {
  reservation: {
    id: string
    code: string
    status: string
    checkin_date: string
    checkout_date: string
    booker: { id: string; full_name: string; document_type: string; document_number: string; email: string }
  }
  billing: {
    bill_to: BillTo
    company: CompanyRef | null
    routing: Route[]
    purchase_order: string
    notes: string
    updated_at: string | null
    updated_by: string | null
  }
  folios: BillingFolio[]
  balances: {
    /** Whole reservation (guest + companies). */
    total: Money
    /** The guest's part. */
    guest: Money
    /** What must be paid before the check-out (companies without credit included). */
    checkout_due: Money
    companies: { company: CompanyRef; expected: Money; credit: boolean; blocks_checkout: boolean }[]
  }
  credit: CreditStatus | null
  routes: Route[]
  /** Only in the answer of a save: charges moved to their folio by the new rules. */
  moved?: number
}

export interface BillingInput {
  bill_to: BillTo
  company_id: string | null
  routing: Route[]
  purchase_order: string
  notes: string
  move_existing: boolean
}

export interface AccountPaymentInput {
  amount: Money
  method: ArMethod
  reference: string
  notes: string
  received_on: string | null
  allocations: { folio_id: string; amount: Money }[]
  auto_allocate: boolean
}

export interface OpeningBalanceInput {
  amount: Money
  document_date: string
  reference: string
  description: string
}

// ---- Query keys -----------------------------------------------------------------------------------

export const corporateKeys = {
  all: ['corporate'] as const,
  companies: (filters: CompanyFilters) => ['corporate', 'companies', filters] as const,
  company: (id: string) => ['corporate', 'company', id] as const,
  statement: (id: string) => ['corporate', 'statement', id] as const,
  reservations: (id: string) => ['corporate', 'company-reservations', id] as const,
  receivables: ['corporate', 'receivables'] as const,
  billing: (reservationId: string) => ['corporate', 'billing', reservationId] as const,
}

const BASE = '/corporate'

// ---- Queries --------------------------------------------------------------------------------------

export function useCompanies(filters: CompanyFilters, enabled = true) {
  return useQuery({
    queryKey: corporateKeys.companies(filters),
    queryFn: ({ signal }) => api.get<Page<Company>>(`${BASE}/companies/`, { params: { ...filters }, signal }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useCompany(id: string) {
  return useQuery({
    queryKey: corporateKeys.company(id),
    queryFn: ({ signal }) => api.get<Company>(`${BASE}/companies/${id}/`, { signal }),
    enabled: Boolean(id),
  })
}

export function useStatement(id: string) {
  return useQuery({
    queryKey: corporateKeys.statement(id),
    queryFn: ({ signal }) => api.get<Statement>(`${BASE}/companies/${id}/statement/`, { signal }),
    enabled: Boolean(id),
  })
}

export function useCompanyReservations(id: string, enabled = true) {
  return useQuery({
    queryKey: corporateKeys.reservations(id),
    queryFn: ({ signal }) => api.get<CompanyReservation[]>(`${BASE}/companies/${id}/reservations/`, { signal }),
    enabled: Boolean(id) && enabled,
  })
}

export function useReceivables() {
  return useQuery({
    queryKey: corporateKeys.receivables,
    queryFn: ({ signal }) => api.get<Receivables>(`${BASE}/receivables/`, { signal }),
  })
}

export function useReservationBilling(reservationId: string) {
  return useQuery({
    queryKey: corporateKeys.billing(reservationId),
    queryFn: ({ signal }) => api.get<ReservationBilling>(`${BASE}/reservations/${reservationId}/billing/`, { signal }),
    enabled: Boolean(reservationId),
  })
}

// ---- Mutations ------------------------------------------------------------------------------------

/** Corporate changes move money between folios and invoices: refresh corporate, finance and compliance data. */
function useCorporateMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: corporateKeys.all }),
        queryClient.invalidateQueries({ queryKey: financeKeys.all }),
        queryClient.invalidateQueries({ queryKey: complianceKeys.all }),
      ])
    },
  })
}

export const useSaveCompany = () =>
  useCorporateMutation(({ id, ...body }: Partial<CompanyInput> & { id?: string }) =>
    id ? api.patch<Company>(`${BASE}/companies/${id}/`, body) : api.post<Company>(`${BASE}/companies/`, body),
  )

export const useDeleteCompany = () => useCorporateMutation((id: string) => api.delete<void>(`${BASE}/companies/${id}/`))

export const useSaveBilling = (reservationId: string) =>
  useCorporateMutation((body: BillingInput) =>
    api.put<ReservationBilling>(`${BASE}/reservations/${reservationId}/billing/`, body),
  )

export const useRecordAccountPayment = (companyId: string) =>
  useCorporateMutation((body: AccountPaymentInput) =>
    api.post<Statement & { payment: AccountPaymentRow | null }>(`${BASE}/companies/${companyId}/payments/`, body),
  )

export const useApplyCredit = (companyId: string) =>
  useCorporateMutation((body: { allocations?: { folio_id: string; amount: Money }[]; auto?: boolean }) =>
    api.post<Statement & { applied: number }>(`${BASE}/companies/${companyId}/apply-credit/`, body),
  )

export const useVoidAccountPayment = () =>
  useCorporateMutation(({ id, reason }: { id: string; reason: string }) =>
    api.post<Statement>(`${BASE}/account-payments/${id}/void/`, { reason, confirm: true }),
  )

export const useAddOpeningBalance = (companyId: string) =>
  useCorporateMutation((body: OpeningBalanceInput) =>
    api.post<Statement & { folio_id: string }>(`${BASE}/companies/${companyId}/opening-balance/`, body),
  )

// ---- Files ----------------------------------------------------------------------------------------

export const downloadStatementCsv = (companyId: string) =>
  api.get<Blob>(`${BASE}/companies/${companyId}/statement/export/`, { responseType: 'blob' })

export const downloadReceivablesCsv = () => api.get<Blob>(`${BASE}/receivables/export/`, { responseType: 'blob' })
