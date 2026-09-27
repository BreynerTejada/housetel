/**
 * Finance API client (backend `apps/finance`, docs/integration-notes/B4-finance.md).
 * Money is always a decimal string ("350000.00"). Other features may import these types and hooks:
 * `useReservationFolios`, `useFolio`, `financeKeys` (invalidate after check-out, etc.).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, isApiError, publicApi } from '@/lib/api'

export type Money = string

export type PaymentMethod =
  | 'cash'
  | 'card_terminal'
  | 'bank_transfer'
  | 'wompi_card'
  | 'wompi_pse'
  | 'wompi_nequi'
  | 'wompi_other'
  | 'ota_collect'
  | 'other'
export type ManualPaymentMethod = 'cash' | 'card_terminal' | 'bank_transfer' | 'other'
export type PaymentStatus = 'pending' | 'approved' | 'declined' | 'voided' | 'error'
export type RefundStatus = 'pending' | 'approved' | 'failed'
export type IntentStatus = 'created' | 'pending' | 'approved' | 'declined' | 'expired' | 'error'
export type ChargeKind = 'room' | 'extra' | 'tax' | 'fee' | 'cancellation_fee' | 'adjustment' | 'other'
export type ManualChargeKind = 'extra' | 'fee' | 'adjustment' | 'other'
export type ExtraChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'
export type LinkChannel = 'email' | 'whatsapp'
export type SimOutcome = 'approved' | 'declined' | 'expired'
export type SimMethod = 'card' | 'pse' | 'nequi'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface UserRef {
  id: string
  full_name: string
  email: string
}

export interface TaxRef {
  id: string
  code: string
  name: string
  rate: string
}

export interface ReservationRef {
  id: string
  code: string
  status: string
  checkin_date: string
  checkout_date: string
  adults: number
  children: number
}

export interface GuestRef {
  id: string
  full_name: string
  email: string
  phone: string
  is_foreign_non_resident: boolean
}

export interface FolioTotals {
  /** Σ net amount of non-voided charges. */
  charges_net: Money
  tax_total: Money
  /** Net + tax. */
  charges_total: Money
  payments_total: Money
  refunds_total: Money
  /** Posted charges − approved payments + approved refunds (this folio only). */
  balance: Money
  /** Whole reservation (stays not yet posted included); only in the folio detail. */
  reservation_balance?: Money | null
}

export interface Charge {
  id: string
  folio: string
  business_date: string
  kind: ChargeKind
  description: string
  quantity: number
  unit_price: Money
  amount: Money
  tax_amount: Money
  total: Money
  tax: TaxRef | null
  tax_exempt: boolean
  stay_id: string | null
  night_date: string | null
  extra_id: string | null
  source: string
  posted_by: UserRef | null
  voided: boolean
  voided_at: string | null
  voided_by: UserRef | null
  void_reason: string
  created_at: string
}

export interface Payment {
  id: string
  folio: string
  business_date: string
  amount: Money
  method: PaymentMethod
  status: PaymentStatus
  provider: string
  provider_reference: string
  notes: string
  received_by: UserRef | null
  refunded_amount: Money
  refundable_amount: Money
  intent_id: string | null
  intent_reference: string | null
  cash_shift_id: string | null
  can_void: boolean
  voided_at: string | null
  void_reason: string
  created_at: string
}

export interface Refund {
  id: string
  payment_id: string
  amount: Money
  status: RefundStatus
  provider_reference: string
  reason: string
  instructions: string
  error: string
  requested_by: UserRef | null
  approved_by: UserRef | null
  business_date: string | null
  created_at: string
  completed_at: string | null
}

export interface PaymentIntent {
  id: string
  reference: string
  folio_id: string
  reservation_id: string | null
  reservation_code: string | null
  amount: Money
  currency: string
  status: IntentStatus
  mode: 'real' | 'simulated'
  provider: string
  checkout_url: string
  return_url: string
  expires_at: string | null
  created_at: string
  method: string
  status_message: string
  last_checked_at: string | null
  payment_id: string | null
}

export interface FolioSummary {
  id: string
  folio_type: 'guest' | 'master' | 'house'
  status: 'open' | 'closed'
  currency: string
  closed_at: string | null
  created_at: string
  reservation: ReservationRef | null
  guest: GuestRef | null
  totals: FolioTotals
}

export interface FolioDetail extends FolioSummary {
  charges: Charge[]
  payments: Payment[]
  refunds: Refund[]
  intents: PaymentIntent[]
}

export interface TaxOption {
  id: string
  code: string
  name: string
  rate: string
  applies_to: string
  included_in_price: boolean
  /** Would be exempt for this folio's guest (foreign non-resident). */
  exempt: boolean
}

export interface ExtraOption {
  id: string
  code: string
  name: Record<string, string>
  price: Money
  /** Net unit price posted to the folio (tax-included prices are split). */
  unit_price: Money
  charge_type: ExtraChargeType
  default_quantity: number
  tax: TaxOption | null
}

export interface ChargeOptions {
  extras: ExtraOption[]
  taxes: TaxOption[]
  manual_kinds: ManualChargeKind[]
  guest_is_foreign_non_resident: boolean
}

export interface MethodTotal {
  method: PaymentMethod
  count: number
  total: Money
}

export interface ShiftTotals {
  opening_float: Money
  cash_payments: Money
  cash_refunds: Money
  expected_cash: Money
  payments_count: number
  refunds_count: number
  by_method: MethodTotal[]
}

export interface ShiftMovement {
  id: string
  kind: 'payment' | 'refund'
  created_at: string
  method: PaymentMethod
  amount: Money
  status: string
  reference: string
  folio_id: string
  reservation_id: string | null
  reservation_code: string | null
  guest_name: string
}

export interface CashShift {
  id: string
  user: UserRef
  opened_at: string
  closed_at: string | null
  is_open: boolean
  opening_float: Money
  expected_cash: Money | null
  counted_cash: Money | null
  difference: Money | null
  denominations: Record<string, number>
  notes: string
  closed_by: UserRef | null
}

export interface CashShiftDetail extends CashShift {
  totals: ShiftTotals
  movements: ShiftMovement[]
}

export interface DaySummary {
  date: string
  currency: string
  payments: { count: number; total: Money }
  refunds: { count: number; total: Money }
  net_total: Money
  by_method: MethodTotal[]
  charges: { net: Money; tax: Money; total: Money }
}

export interface OutboundMessageResult {
  channel: string
  to: string
  status: string
  error: string
}

export interface PaymentLinkResult {
  intent: PaymentIntent
  checkout_url: string
  messages: OutboundMessageResult[]
  send_error?: string
}

export interface SimIntent {
  reference: string
  amount: Money
  currency: string
  status: IntentStatus | string
  mode: string
  method: string
  expires_at: string | null
  created_at: string
  /** Where to send the guest back (already carries `payment_ref`); empty when there is none. */
  return_url: string
  property: { name: string; slug: string; city: string; primary_color: string; logo: string }
  reservation_code: string | null
  payer_first_name: string | null
}

/** `GET /public/finance/intents/<reference>/status/` (the server verifies with the provider first). */
export interface PaymentLinkStatus {
  reference: string
  status: IntentStatus
  paid: boolean
  amount: Money
  currency: string
  method: string
  reservation_code: string | null
  property_slug: string
}

// ---- Query keys -----------------------------------------------------------------------------------

export const financeKeys = {
  all: ['finance'] as const,
  reservationFolios: (reservationId: string) => ['finance', 'folios', { reservation: reservationId }] as const,
  folio: (folioId: string) => ['finance', 'folio', folioId] as const,
  chargeOptions: (folioId: string) => ['finance', 'charge-options', folioId] as const,
  currentShift: () => ['finance', 'cash-shifts', 'current'] as const,
  shifts: (page: number) => ['finance', 'cash-shifts', 'list', page] as const,
  summary: (date: string | undefined) => ['finance', 'summary', date ?? 'today'] as const,
  simIntent: (reference: string) => ['finance', 'sim', reference] as const,
  paymentStatus: (reference: string) => ['finance', 'payment-status', reference] as const,
}

// ---- Folios ---------------------------------------------------------------------------------------

export const getReservationFolios = (reservationId: string) =>
  api.get<Page<FolioSummary>>('/finance/folios/', { params: { reservation: reservationId, page_size: 50 } })

export const ensureFolio = (reservationId: string) =>
  api.post<FolioDetail>('/finance/folios/', { reservation_id: reservationId })

export const getFolio = (folioId: string) => api.get<FolioDetail>(`/finance/folios/${folioId}/`)

export const getChargeOptions = (folioId: string) => api.get<ChargeOptions>(`/finance/folios/${folioId}/charge-options/`)

export type ChargeInput =
  | { extra_id: string; quantity?: number }
  | { kind: ManualChargeKind; description: string; amount: Money; quantity?: number; tax_id?: string | null }

export const postCharge = (folioId: string, input: ChargeInput) =>
  api.post<Charge>(`/finance/folios/${folioId}/charges/`, input)

export const voidCharge = (chargeId: string, reason: string) =>
  api.post<Charge>(`/finance/charges/${chargeId}/void/`, { reason, confirm: true })

export interface ManualPaymentInput {
  amount: Money
  method: ManualPaymentMethod
  reference: string
  notes: string
}

export const recordPayment = (folioId: string, input: ManualPaymentInput) =>
  api.post<Payment>(`/finance/folios/${folioId}/payments/`, input)

export const voidPayment = (paymentId: string, reason: string) =>
  api.post<Payment>(`/finance/payments/${paymentId}/void/`, { reason, confirm: true })

export const refundPayment = (paymentId: string, amount: Money, reason: string) =>
  api.post<Refund>(`/finance/payments/${paymentId}/refund/`, { amount, reason, confirm: true })

export const completeRefund = (refundId: string, outcome: 'approved' | 'failed', reference: string) =>
  api.post<Refund>(`/finance/refunds/${refundId}/complete/`, { confirm: true, outcome, reference })

export const createPaymentLink = (folioId: string, amount: Money, sendVia: LinkChannel[]) =>
  api.post<PaymentLinkResult>(`/finance/folios/${folioId}/payment-link/`, { amount, send_via: sendVia })

export const syncIntent = (intentId: string) => api.post<PaymentIntent>(`/finance/intents/${intentId}/sync/`)

// ---- Cash shifts ----------------------------------------------------------------------------------

export const getCurrentShift = () => api.get<{ shift: CashShiftDetail | null }>('/finance/cash-shifts/current/')

export const openShift = (openingFloat: Money, notes: string) =>
  api.post<CashShiftDetail>('/finance/cash-shifts/open/', { opening_float: openingFloat, notes })

export type CloseShiftInput =
  | { denominations: Record<string, number>; notes: string }
  | { counted_cash: Money; notes: string }

export const closeShift = (shiftId: string, input: CloseShiftInput) =>
  api.post<CashShiftDetail>(`/finance/cash-shifts/${shiftId}/close/`, input)

export const getShifts = (page: number) =>
  api.get<Page<CashShift>>('/finance/cash-shifts/', { params: { page, page_size: 10 } })

export const getShift = (shiftId: string) => api.get<CashShiftDetail>(`/finance/cash-shifts/${shiftId}/`)

export const downloadShiftCsv = (shiftId: string) =>
  api.get<Blob>(`/finance/cash-shifts/${shiftId}/export/`, { responseType: 'blob' })

export const downloadShiftsCsv = (start: string, end: string) =>
  api.get<Blob>('/finance/cash-shifts/export/', { params: { start, end }, responseType: 'blob' })

export const getDaySummary = (date?: string) => api.get<DaySummary>('/finance/summary/', { params: { date } })

// ---- Simulated gateway (public) -------------------------------------------------------------------

export const getSimIntent = (reference: string) =>
  publicApi.get<SimIntent>(`/finance/sim/intents/${encodeURIComponent(reference)}/`)

export const decideSimIntent = (reference: string, outcome: SimOutcome, method: SimMethod) =>
  publicApi.post<SimIntent>(`/finance/sim/intents/${encodeURIComponent(reference)}/decide/`, { outcome, method })

// ---- Return pages (public): C4 `/booking/:code/confirmed`, C5 `/g/:token?paid=1` ----------------------

export const getPaymentStatus = (reference: string, transactionId?: string | null) =>
  publicApi.get<PaymentLinkStatus>(`/finance/intents/${encodeURIComponent(reference)}/status/`, {
    params: { id: transactionId },
  })

/**
 * What the gateway sends back in the return URL: `payment_ref` (added by Housetel to every link) and
 * `id` (the transaction id Wompi appends; the simulated gateway does not send it).
 */
export function paymentReturnParams(search: string | URLSearchParams): { reference: string | null; transactionId: string | null } {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search
  return { reference: params.get('payment_ref') || null, transactionId: params.get('id') || null }
}

const DECIDED_STATUSES: IntentStatus[] = ['approved', 'declined', 'expired', 'error']

/**
 * State of a payment link for the page the guest returns to. Asks every `intervalMs` (the server verifies
 * with Wompi on each call) until the payment is decided (approved / declined / expired / error), the server
 * does not know the reference, or `maxPolls` answers arrived. No request without a reference.
 */
export function usePaymentStatus(
  reference: string | null | undefined,
  { transactionId = null, intervalMs = 3000, maxPolls = 200 }: { transactionId?: string | null; intervalMs?: number; maxPolls?: number } = {},
) {
  return useQuery({
    queryKey: financeKeys.paymentStatus(reference ?? ''),
    queryFn: () => getPaymentStatus(reference!, transactionId),
    enabled: Boolean(reference),
    refetchInterval: (query) => {
      const { data, error, dataUpdateCount } = query.state
      if (data && DECIDED_STATUSES.includes(data.status)) return false
      if (isApiError(error) && error.status >= 400 && error.status < 500) return false
      return dataUpdateCount >= maxPolls ? false : intervalMs
    },
  })
}

// ---- Hooks ----------------------------------------------------------------------------------------

/** Folios of a reservation (usually one guest folio). */
export function useReservationFolios(reservationId: string) {
  return useQuery({
    queryKey: financeKeys.reservationFolios(reservationId),
    queryFn: () => getReservationFolios(reservationId),
    enabled: Boolean(reservationId),
  })
}

/** Folio with its lines, payments, refunds, links and totals. */
export function useFolio(folioId: string | null | undefined) {
  return useQuery({
    queryKey: financeKeys.folio(folioId ?? ''),
    queryFn: () => getFolio(folioId!),
    enabled: Boolean(folioId),
    placeholderData: keepPreviousData,
  })
}

export function useCurrentShift(enabled = true) {
  return useQuery({ queryKey: financeKeys.currentShift(), queryFn: getCurrentShift, enabled })
}

/** Every finance mutation refreshes all finance queries (folios, shifts, summaries). */
export function useFinanceMutation<TVariables, TResult>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
  { onSuccess }: { onSuccess?: (result: TResult, variables: TVariables) => void } = {},
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async (result, variables) => {
      await queryClient.invalidateQueries({ queryKey: financeKeys.all })
      onSuccess?.(result, variables)
    },
  })
}
