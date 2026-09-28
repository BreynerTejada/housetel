/**
 * SaaS data layer (backend `/api/v1/saas/…` and `/api/v1/public/saas/…`, see docs/integration-notes/C11-saas.md):
 * hotel billing, getting-started checklist, signup and the platform super-admin.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { api, publicApi } from '@/lib/api'
import { ME_QUERY_KEY, type Me } from '@/lib/auth'
import { useSession } from '@/lib/session'

export type I18nText = { es?: string; en?: string }

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type SubscriptionStatus = 'trialing' | 'active' | 'past_due' | 'suspended' | 'cancelled'
export type OrganizationStatus = 'trial' | 'active' | 'past_due' | 'suspended' | 'cancelled'
export type BillingCycle = 'monthly' | 'yearly'
export type InvoiceStatus = 'open' | 'paid' | 'void' | 'failed'
export type InvoiceKind = 'subscription' | 'commissions' | 'other'
export type CommissionStatus = 'pending' | 'settled' | 'reversed'
export type SettlementStatus = 'open' | 'invoiced' | 'paid'

export interface PlanRef {
  id: string
  code: string
  name: I18nText
  max_units: number | null
  max_properties: number | null
  price_monthly: string
  price_yearly: string
}

export interface Plan extends PlanRef {
  description: I18nText
  is_active: boolean
  sort: number
  subscriptions_count?: number
  active_subscriptions_count?: number
  created_at?: string
}

export interface PublicPlan {
  code: string
  name: I18nText
  description: I18nText
  max_units: number | null
  max_properties: number | null
  price_monthly: string
  price_yearly: string
}

export interface BillingPlanOption extends PlanRef {
  description: I18nText
  fits: boolean
  current: boolean
}

export interface PaymentSource {
  type: string | null
  brand: string | null
  last4: string | null
  exp_month: number | null
  exp_year: number | null
  holder: string | null
  simulated: boolean | null
}

export interface Subscription {
  id: string
  plan: PlanRef
  status: SubscriptionStatus
  billing_cycle: BillingCycle
  current_period_start: string | null
  current_period_end: string | null
  trial_ends_at: string | null
  cancel_at_period_end: boolean
  payment_source: PaymentSource | null
  retries: number
  next_retry_at: string | null
  past_due_since: string | null
  cancelled_at: string | null
  monthly_amount: string
}

export interface InvoiceLine {
  kind: 'plan' | 'commission' | 'adjustment'
  description: I18nText
  quantity: number
  unit_price: string
  amount: string
  property_id?: string
  settlement_id?: string
  plan_code?: string
}

export interface PlatformInvoice {
  id: string
  number: string
  kind: InvoiceKind
  organization: { id: string; name: string; slug: string }
  period_start: string
  period_end: string
  lines: InvoiceLine[]
  currency: string
  subtotal: string
  tax_rate: string
  tax: string
  total: string
  status: InvoiceStatus
  issued_at: string
  due_date: string
  paid_at: string | null
  payment_reference: string
  payment_method: string
  attempts: number
  last_error: string
}

export interface Usage {
  units: number
  properties: number
  max_units: number | null
  max_properties: number | null
  units_percent: number | null
  over_limit: boolean
}

export interface BillingSummary {
  organization_status: OrganizationStatus
  subscription_status: SubscriptionStatus | null
  plan: { code: string; name: I18nText } | null
  trial_ends_at: string | null
  trial_days_left: number | null
  open_balance: string
}

export interface UpcomingInvoice {
  date: string
  period_start: string
  period_end: string
  subtotal: string
  tax: string
  total: string
}

export interface BillingOverview {
  organization: { id: string; name: string; status: OrganizationStatus; trial_ends_at: string | null }
  subscription: Subscription
  summary: BillingSummary
  usage: Usage
  upcoming_invoice: UpcomingInvoice | null
  open_invoices: PlatformInvoice[]
  plans: BillingPlanOption[]
  billing_mode: 'real' | 'simulated'
  tax_rate: string
  retry_schedule_days: number[]
}

export interface CommissionTotals {
  total: string
  count: number
}

export type CommissionSummary = Record<CommissionStatus, CommissionTotals>

export interface Commission {
  id: string
  organization: { id: string; name: string }
  property: { id: string; name: string; slug: string }
  reservation: {
    id: string
    code: string
    status: string
    checkin_date: string
    checkout_date: string
    total_amount: string
  }
  basis: 'stay' | 'fee'
  base_amount: string
  rate: string
  amount: string
  currency: string
  status: CommissionStatus
  accrual_date: string
  settlement_id: string | null
  reversed_at: string | null
  created_at: string
}

export interface Settlement {
  id: string
  organization: { id: string; name: string; slug: string }
  period_start: string
  period_end: string
  total: string
  commissions_count: number
  status: SettlementStatus
  invoice: { id: string; number: string; status: InvoiceStatus } | null
  created_at: string
}

export interface HotelCommissions {
  summary: CommissionSummary
  this_month: CommissionSummary
  rates: { property_id: string; name: string; commission_rate: string; marketplace_listed: boolean }[]
  settlements: Settlement[]
  recent: Commission[]
}

export type StepId = 'profile' | 'rooms' | 'rates' | 'payments' | 'channels' | 'team' | 'first_booking'

export interface ChecklistStep {
  id: StepId
  done: boolean
  detail: Record<string, unknown>
  link: string
  alt_link?: string
}

export interface GettingStarted {
  property: { id: string; name: string; slug: string }
  steps: ChecklistStep[]
  completed: number
  total: number
  percent: number
  billing: BillingSummary
}

// ---- Admin ---------------------------------------------------------------------------------------

export interface MetricsSeriesPoint {
  month: string
  subscriptions: string
  commissions: string
  gmv: string
  bookings: number
  new_organizations: number
}

export interface PlatformMetrics {
  as_of: string
  currency: string
  mrr: string
  arr: string
  trial_mrr: string
  organizations: Record<'total' | OrganizationStatus, number>
  churn_30d: number
  cancelled_30d: number
  gmv_month: string
  commissions_month: string
  commissions_pending: string
  unpaid_invoices: { count: number; total: string }
  series: MetricsSeriesPoint[]
  plan_mix: { plan: string; count: number }[]
}

export interface OrganizationRow {
  id: string
  name: string
  slug: string
  legal_name: string
  nit: string
  status: OrganizationStatus
  created_at: string
  /** Organization creation or its first trial start, whichever is earlier (YYYY-MM-DD). */
  customer_since: string
  trial_ends_at: string | null
  subscription: {
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    current_period_end: string | null
    cancel_at_period_end: boolean
    has_payment_method: boolean
  } | null
  plan: { code: string; name: I18nText; max_units: number | null } | null
  units: number
  properties_count: number | null
  users_count: number | null
  mrr: string
  simulate_payment_failure: boolean
}

export interface OrganizationDetail extends OrganizationRow {
  properties: {
    id: string
    name: string
    slug: string
    city: string
    department: string
    property_type: string
    status: string
    units: number
    reservations: number
    marketplace_listed: boolean
    commission_rate: string
    business_date: string
  }[]
  users: {
    id: string
    email: string
    full_name: string
    role: { code: string; name: string }
    is_active: boolean
    all_properties: boolean
    last_login: string | null
  }[]
  pending_invitations: number
  subscription_detail: Subscription | null
  usage: Usage | null
  upcoming_invoice: UpcomingInvoice | null
  invoices: PlatformInvoice[]
  commissions: { summary: CommissionSummary; recent: Commission[] }
  settlements: Settlement[]
}

export interface BillingSettings {
  mode: 'real' | 'simulated'
  enabled: boolean
  /** P-INT: false = the daily billing cycle charges nobody (real mode without WOMPI_PLATFORM_* or switched off). */
  collection_available?: boolean
  status: 'unknown' | 'ok' | 'error'
  status_message: string
  last_checked_at: string | null
  wompi: {
    environment: string
    public_key_configured: boolean
    private_key_configured: boolean
    integrity_secret_configured: boolean
    events_secret_configured: boolean
    webhook_url: string
  }
}

export interface SignupPayload {
  hotel_name: string
  property_type: string
  city: string
  department: string
  rooms_estimate: number
  owner_name: string
  email: string
  password: string
  phone: string
  accept_terms: boolean
  language: 'es' | 'en'
}

export interface SignupResponse {
  redirect: string
  organization: { id: string; slug: string }
  property: { id: string; slug: string }
  me: Me
}

export interface PayResult {
  status: 'approved' | 'declined' | 'pending' | 'requires_action' | 'error' | 'void'
  checkout_url: string | null
  message: string
  invoice: PlatformInvoice
}

// ---- Keys ----------------------------------------------------------------------------------------

export const saasKeys = {
  all: ['saas'] as const,
  billing: () => ['saas', 'billing'] as const,
  status: () => ['saas', 'status'] as const,
  invoices: () => ['saas', 'invoices'] as const,
  commissions: () => ['saas', 'commissions'] as const,
  checklist: () => ['saas', 'getting-started'] as const,
  publicPlans: () => ['saas-public', 'plans'] as const,
  admin: ['saas-admin'] as const,
  metrics: () => ['saas-admin', 'metrics'] as const,
  orgs: (params: Record<string, unknown>) => ['saas-admin', 'orgs', params] as const,
  org: (id: string) => ['saas-admin', 'org', id] as const,
  plans: () => ['saas-admin', 'plans'] as const,
  adminInvoices: (params: Record<string, unknown>) => ['saas-admin', 'invoices', params] as const,
  adminCommissions: (params: Record<string, unknown>) => ['saas-admin', 'commissions', params] as const,
  settlements: () => ['saas-admin', 'settlements'] as const,
  billingSettings: () => ['saas-admin', 'billing-settings'] as const,
}

// ---- Hotel (staff) -------------------------------------------------------------------------------

export function useBillingOverview() {
  return useQuery({ queryKey: saasKeys.billing(), queryFn: () => api.get<BillingOverview>('/saas/billing/') })
}

/** Topbar chip: any member can read it; refreshed every 5 minutes. */
export function useBillingStatus(enabled = true) {
  return useQuery({
    queryKey: saasKeys.status(),
    queryFn: () => api.get<BillingSummary>('/saas/billing/status/'),
    enabled,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  })
}

export function useInvoices() {
  return useQuery({ queryKey: saasKeys.invoices(), queryFn: () => api.get<PlatformInvoice[]>('/saas/billing/invoices/') })
}

export function useHotelCommissions() {
  return useQuery({ queryKey: saasKeys.commissions(), queryFn: () => api.get<HotelCommissions>('/saas/billing/commissions/') })
}

export function useGettingStarted() {
  return useQuery({ queryKey: saasKeys.checklist(), queryFn: () => api.get<GettingStarted>('/saas/getting-started/') })
}

function useInvalidateBilling() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: saasKeys.all }),
      // The organization status lives in `Me` (topbar, guards): refresh it after billing changes.
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
    ])
}

export function usePayInvoice() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: (id: string) => api.post<PayResult>(`/saas/billing/invoices/${id}/pay/`),
    onSuccess: () => invalidate(),
  })
}

export function useVerifyInvoice() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: (id: string) => api.post<PlatformInvoice>(`/saas/billing/invoices/${id}/verify/`),
    onSuccess: () => invalidate(),
  })
}

export interface CardPayload {
  holder: string
  number: string
  exp_month: number
  exp_year: number
  cvc: string
}

/** Real mode: the card was tokenized by Wompi in the browser; only tokens reach Housetel. */
export interface WompiCardPayload {
  token: string
  acceptance_token: string
  accept_personal_auth: string
}

export type PaymentMethodSetup =
  | { mode: 'simulated' }
  | {
      mode: 'real'
      public_key: string
      environment: string
      tokenize_url: string
      acceptance_token: string
      acceptance_permalink: string
      personal_auth_token: string
      personal_auth_permalink: string
    }

export function usePaymentMethodSetup(enabled: boolean) {
  return useQuery({
    queryKey: [...saasKeys.all, 'payment-method-setup'] as const,
    queryFn: () => api.get<PaymentMethodSetup>('/saas/billing/payment-method/'),
    enabled,
    staleTime: 60_000,
  })
}

export function useSavePaymentMethod() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: (payload: CardPayload | WompiCardPayload) => api.post<Subscription>('/saas/billing/payment-method/', payload),
    onSuccess: () => invalidate(),
  })
}

export function useRemovePaymentMethod() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: () => api.delete<Subscription>('/saas/billing/payment-method/'),
    onSuccess: () => invalidate(),
  })
}

/**
 * Wompi card tokenization (docs.wompi.co › Fuentes de pago): `POST /v1/tokens/cards` with the platform's
 * public key; the card number never touches Housetel's servers. Returns the token id (`data.id`).
 */
export async function tokenizeCard(
  setup: Extract<PaymentMethodSetup, { mode: 'real' }>,
  card: CardPayload,
): Promise<string> {
  const response = await fetch(setup.tokenize_url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${setup.public_key}` },
    body: JSON.stringify({
      number: card.number.replace(/\D/g, ''),
      cvc: card.cvc,
      exp_month: String(card.exp_month).padStart(2, '0'),
      exp_year: String(card.exp_year % 100).padStart(2, '0'),
      card_holder: card.holder,
    }),
  })
  const body = (await response.json().catch(() => ({}))) as {
    data?: { id?: string }
    error?: { messages?: Record<string, string[]>; reason?: string }
  }
  if (!response.ok || !body.data?.id) {
    const messages = body.error?.messages ? Object.values(body.error.messages).flat() : []
    throw new Error(messages[0] ?? body.error?.reason ?? 'card_tokenization_failed')
  }
  return body.data.id
}

export function useChangePlan() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: (payload: { plan_code: string; billing_cycle: BillingCycle }) =>
      api.post<Subscription>('/saas/billing/change-plan/', payload),
    onSuccess: () => invalidate(),
  })
}

export function useCancelSubscription() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: (reason: string) => api.post<Subscription>('/saas/billing/cancel/', { confirm: true, reason }),
    onSuccess: () => invalidate(),
  })
}

export function useResumeSubscription() {
  const invalidate = useInvalidateBilling()
  return useMutation({
    mutationFn: () => api.post<Subscription>('/saas/billing/resume/'),
    onSuccess: () => invalidate(),
  })
}

/** Download a staff PDF (needs the X-Property-Id header, so no plain `<a href>`). */
export async function downloadInvoicePdf(invoice: PlatformInvoice, lang: string, admin = false): Promise<void> {
  const path = admin ? `/saas/admin/invoices/${invoice.id}/pdf/` : `/saas/billing/invoices/${invoice.id}/pdf/`
  const blob = await api.get<Blob>(path, { params: { lang }, responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${invoice.number}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// ---- Public --------------------------------------------------------------------------------------

export function usePublicPlans() {
  return useQuery({
    queryKey: saasKeys.publicPlans(),
    queryFn: () => publicApi.get<PublicPlan[]>('/saas/plans/'),
    staleTime: 10 * 60_000,
  })
}

/**
 * Signup starts the new owner's session: whatever was cached for someone else on this device is dropped
 * (and their active hotel forgotten) before storing the new `Me` and selecting the new hotel.
 */
export function useSignup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SignupPayload) => publicApi.post<SignupResponse>('/saas/signup/', payload),
    onSuccess: async (result) => {
      const stale = (query: Query) => query.queryKey[0] !== ME_QUERY_KEY[0] && query.queryKey[0] !== 'saas-public'
      await queryClient.cancelQueries({ predicate: stale })
      queryClient.removeQueries({ predicate: stale })
      useSession.getState().setLoggedOut(false)
      useSession.getState().setPropertyId(result.property.id)
      queryClient.setQueryData(ME_QUERY_KEY, result.me)
    },
  })
}

// ---- Platform admin ------------------------------------------------------------------------------

export function useMetrics() {
  return useQuery({ queryKey: saasKeys.metrics(), queryFn: () => api.get<PlatformMetrics>('/saas/admin/metrics/') })
}

export interface OrgFilters {
  status?: string
  plan?: string
  q?: string
  page?: number
  page_size?: number
}

export function useOrganizations(filters: OrgFilters) {
  return useQuery({
    queryKey: saasKeys.orgs(filters as Record<string, unknown>),
    queryFn: () => api.get<Page<OrganizationRow>>('/saas/admin/organizations/', { params: { ...filters } }),
    placeholderData: keepPreviousData,
  })
}

export function useOrganization(id: string) {
  return useQuery({ queryKey: saasKeys.org(id), queryFn: () => api.get<OrganizationDetail>(`/saas/admin/organizations/${id}/`) })
}

function useOrgAction<P>(id: string, path: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: P) => api.post<OrganizationDetail>(`/saas/admin/organizations/${id}/${path}/`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(saasKeys.org(id), data)
      void queryClient.invalidateQueries({ queryKey: saasKeys.admin })
    },
  })
}

export const useSuspendOrganization = (id: string) => useOrgAction<{ confirm: true; reason: string }>(id, 'suspend')
export const useReactivateOrganization = (id: string) => useOrgAction<Record<string, never>>(id, 'reactivate')
export const useExtendTrial = (id: string) => useOrgAction<{ days: number }>(id, 'extend-trial')
export const useEndTrial = (id: string) => useOrgAction<Record<string, never>>(id, 'end-trial')
export const useAdminChangePlan = (id: string) =>
  useOrgAction<{ plan_code: string; billing_cycle: BillingCycle }>(id, 'change-plan')
export const useSimulateFailure = (id: string) => useOrgAction<{ enabled: boolean }>(id, 'simulate-payment-failure')

export function usePlans() {
  return useQuery({ queryKey: saasKeys.plans(), queryFn: () => api.get<Plan[]>('/saas/admin/plans/') })
}

export type PlanPayload = Pick<
  Plan,
  'code' | 'name' | 'description' | 'max_units' | 'max_properties' | 'price_monthly' | 'price_yearly' | 'is_active' | 'sort'
>

export function useSavePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: PlanPayload & { id?: string }) =>
      id ? api.patch<Plan>(`/saas/admin/plans/${id}/`, payload) : api.post<Plan>('/saas/admin/plans/', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: saasKeys.admin }),
  })
}

export function useDeletePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/saas/admin/plans/${id}/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: saasKeys.admin }),
  })
}

export interface InvoiceFilters {
  status?: string
  kind?: string
  organization?: string
  q?: string
  page?: number
  page_size?: number
}

export function useAdminInvoices(filters: InvoiceFilters) {
  return useQuery({
    queryKey: saasKeys.adminInvoices(filters as Record<string, unknown>),
    queryFn: () =>
      api.get<Page<PlatformInvoice> & { summary: { open_total: string; paid_month: string } }>('/saas/admin/invoices/', {
        params: { ...filters },
      }),
    placeholderData: keepPreviousData,
  })
}

function useInvoiceAction<P>(path: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: P & { id: string }) => api.post<unknown>(`/saas/admin/invoices/${id}/${path}/`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: saasKeys.admin }),
  })
}

export const useMarkInvoicePaid = () => useInvoiceAction<{ confirm: true; reference?: string }>('mark-paid')
export const useVoidInvoice = () => useInvoiceAction<{ confirm: true; reason?: string }>('void')
export const useChargeInvoice = () => useInvoiceAction<object>('charge')

export interface CommissionFilters {
  status?: string
  organization?: string
  month?: string
  q?: string
  page?: number
  page_size?: number
}

export function useAdminCommissions(filters: CommissionFilters) {
  return useQuery({
    queryKey: saasKeys.adminCommissions(filters as Record<string, unknown>),
    queryFn: () =>
      api.get<Page<Commission> & { summary: CommissionSummary }>('/saas/admin/commissions/', { params: { ...filters } }),
    placeholderData: keepPreviousData,
  })
}

export function useSettlements() {
  return useQuery({
    queryKey: saasKeys.settlements(),
    queryFn: () => api.get<Page<Settlement>>('/saas/admin/settlements/', { params: { page_size: 100 } }),
  })
}

export function useRunSettlement() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (month: string) =>
      api.post<{ run: { id: string; status: string; summary: string }; settlements: Settlement[] }>(
        '/saas/admin/settlements/run/',
        { month },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: saasKeys.admin }),
  })
}

export function useRunBillingCycle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ id: string; status: string; summary: string; details: Record<string, unknown> }>(
        '/saas/admin/billing-cycle/run/',
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: saasKeys.admin }),
  })
}

export function useBillingSettings() {
  return useQuery({ queryKey: saasKeys.billingSettings(), queryFn: () => api.get<BillingSettings>('/saas/admin/billing-settings/') })
}

export function useUpdateBillingSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Pick<BillingSettings, 'mode' | 'enabled'>>) =>
      api.patch<BillingSettings>('/saas/admin/billing-settings/', payload),
    onSuccess: (data) => queryClient.setQueryData(saasKeys.billingSettings(), data),
  })
}

export function useTestBillingSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<BillingSettings>('/saas/admin/billing-settings/test/'),
    onSuccess: (data) => queryClient.setQueryData(saasKeys.billingSettings(), data),
  })
}
