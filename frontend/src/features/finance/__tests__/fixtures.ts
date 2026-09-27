import type {
  CashShiftDetail,
  Charge,
  FolioDetail,
  FolioSummary,
  Payment,
  PaymentIntent,
  SimIntent,
} from '../api'

export const RESERVATION_ID = '9b2f6d1e-0000-4000-8000-00000000r001'
export const FOLIO_ID = '9b2f6d1e-0000-4000-8000-00000000f001'

const reservation = {
  id: RESERVATION_ID,
  code: 'HT-7K2M9Q',
  status: 'checked_in',
  checkin_date: '2026-09-24',
  checkout_date: '2026-09-26',
  adults: 2,
  children: 0,
}

const guest = {
  id: 'guest-1',
  full_name: 'Camila Rodríguez',
  email: 'camila@example.com',
  phone: '+573001112233',
  is_foreign_non_resident: false,
}

export function makeCharge(overrides: Partial<Charge> = {}): Charge {
  return {
    id: 'charge-1',
    folio: FOLIO_ID,
    business_date: '2026-09-24',
    kind: 'room',
    description: 'Noche · Estándar',
    quantity: 1,
    unit_price: '294118.00',
    amount: '294118.00',
    tax_amount: '55882.00',
    total: '350000.00',
    tax: { id: 'tax-1', code: 'IVA', name: 'IVA 19%', rate: '19.00' },
    tax_exempt: false,
    stay_id: null,
    night_date: '2026-09-24',
    extra_id: null,
    source: 'automation',
    posted_by: null,
    voided: false,
    voided_at: null,
    voided_by: null,
    void_reason: '',
    created_at: '2026-09-24T20:00:00-05:00',
    ...overrides,
  }
}

export function makePayment(overrides: Partial<Payment> = {}): Payment {
  return {
    id: 'payment-1',
    folio: FOLIO_ID,
    business_date: '2026-09-24',
    amount: '300000.00',
    method: 'card_terminal',
    status: 'approved',
    provider: 'manual',
    provider_reference: 'VOUCHER-1',
    notes: '',
    received_by: { id: 'user-1', full_name: 'Andrés Gómez', email: 'recepcion@casaaurora.co' },
    refunded_amount: '0.00',
    refundable_amount: '300000.00',
    intent_id: null,
    intent_reference: null,
    cash_shift_id: null,
    can_void: true,
    voided_at: null,
    void_reason: '',
    created_at: '2026-09-24T15:10:00-05:00',
    ...overrides,
  }
}

export function makeIntent(overrides: Partial<PaymentIntent> = {}): PaymentIntent {
  return {
    id: 'intent-1',
    reference: 'HT-7K2M9Q-4F7H2K',
    folio_id: FOLIO_ID,
    reservation_id: RESERVATION_ID,
    reservation_code: 'HT-7K2M9Q',
    amount: '141650.00',
    currency: 'COP',
    status: 'created',
    mode: 'simulated',
    provider: 'simulated',
    checkout_url: 'http://localhost:5173/sim/pay/HT-7K2M9Q-4F7H2K',
    return_url: 'http://localhost:5173/g/tok?paid=1',
    expires_at: '2026-09-26T20:00:00Z',
    created_at: '2026-09-25T20:00:00Z',
    method: '',
    status_message: '',
    last_checked_at: null,
    payment_id: null,
    ...overrides,
  }
}

/** Stay of 700.000 + breakfast 83.300 + minibar voided; 300.000 paid by card terminal → owes 483.300. */
export function makeFolio(overrides: Partial<FolioDetail> = {}): FolioDetail {
  return {
    id: FOLIO_ID,
    folio_type: 'guest',
    status: 'open',
    currency: 'COP',
    closed_at: null,
    created_at: '2026-09-20T10:00:00-05:00',
    reservation,
    guest,
    totals: {
      charges_net: '364118.00',
      tax_total: '69182.00',
      charges_total: '433300.00',
      payments_total: '300000.00',
      refunds_total: '0.00',
      balance: '133300.00',
      reservation_balance: '483300.00',
    },
    charges: [
      makeCharge(),
      makeCharge({
        id: 'charge-2',
        kind: 'extra',
        description: 'Desayuno',
        quantity: 2,
        unit_price: '35000.00',
        amount: '70000.00',
        tax_amount: '13300.00',
        total: '83300.00',
        night_date: null,
        source: 'user',
        tax: { id: 'tax-2', code: 'IVA-EXT', name: 'IVA extras', rate: '19.00' },
      }),
      makeCharge({
        id: 'charge-3',
        kind: 'extra',
        description: 'Minibar',
        amount: '50000.00',
        unit_price: '50000.00',
        tax_amount: '0.00',
        total: '50000.00',
        tax: null,
        voided: true,
        voided_at: '2026-09-25T09:00:00-05:00',
        void_reason: 'No lo consumió',
      }),
    ],
    payments: [makePayment()],
    refunds: [],
    intents: [],
    ...overrides,
  }
}

export function summaryOf(folio: FolioDetail): FolioSummary {
  const { id, folio_type, status, currency, closed_at, created_at, reservation: r, guest: g, totals } = folio
  const { reservation_balance: _ignored, ...summaryTotals } = totals
  return { id, folio_type, status, currency, closed_at, created_at, reservation: r, guest: g, totals: summaryTotals }
}

export function makeShift(overrides: Partial<CashShiftDetail> = {}): CashShiftDetail {
  return {
    id: 'shift-1',
    user: { id: 'user-1', full_name: 'Andrés Gómez', email: 'recepcion@casaaurora.co' },
    opened_at: '2026-09-25T07:00:00-05:00',
    closed_at: null,
    is_open: true,
    opening_float: '200000.00',
    expected_cash: null,
    counted_cash: null,
    difference: null,
    denominations: {},
    notes: '',
    closed_by: null,
    totals: {
      opening_float: '200000.00',
      cash_payments: '120000.00',
      cash_refunds: '20000.00',
      expected_cash: '300000.00',
      payments_count: 3,
      refunds_count: 1,
      by_method: [
        { method: 'card_terminal', count: 1, total: '450000.00' },
        { method: 'cash', count: 2, total: '120000.00' },
      ],
    },
    movements: [
      {
        id: 'mv-1',
        kind: 'payment',
        created_at: '2026-09-25T08:15:00-05:00',
        method: 'cash',
        amount: '100000.00',
        status: 'approved',
        reference: '',
        folio_id: FOLIO_ID,
        reservation_id: RESERVATION_ID,
        reservation_code: 'HT-7K2M9Q',
        guest_name: 'Camila Rodríguez',
      },
    ],
    ...overrides,
  }
}

export function makeSimIntent(overrides: Partial<SimIntent> = {}): SimIntent {
  return {
    reference: 'HT-7K2M9Q-4F7H2K',
    amount: '350000.00',
    currency: 'COP',
    status: 'created',
    mode: 'simulated',
    method: '',
    expires_at: '2099-09-26T20:00:00Z',
    created_at: '2026-09-25T20:00:00Z',
    return_url: 'http://localhost:5173/g/tok?paid=1&payment_ref=HT-7K2M9Q-4F7H2K',
    property: { name: 'Hotel Casa Aurora', slug: 'casa-aurora', city: 'Cartagena', primary_color: '#B4583B', logo: '' },
    reservation_code: 'HT-7K2M9Q',
    payer_first_name: 'Camila',
    ...overrides,
  }
}
