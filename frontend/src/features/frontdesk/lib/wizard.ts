import { addDays, isValid, parse } from 'date-fns'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { toISODate } from '@/lib/format'
import type { OfferQuery, ReservationCreateInput, ReservationSource, StayRequestInput } from '../api'

/**
 * The new-reservation wizard (plan C1): five steps over one state object —
 * 0 dates & guests · 1 rate (offer) · 2 guest · 3 extras & notes · 4 guarantee & payment.
 * Pure helpers (validation per step, payload for `POST /bookings/reservations/`) so they are tested alone.
 */
export const WIZARD_STEPS = ['dates', 'offer', 'guest', 'extras', 'payment'] as const
export type WizardStep = 0 | 1 | 2 | 3 | 4

export type PaymentMode = 'none' | 'payment' | 'link'
export type ManualMethod = 'cash' | 'card_terminal' | 'bank_transfer' | 'other'
export type BookingSource = Extract<ReservationSource, 'front_desk' | 'phone' | 'email'>
export type ExtraChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'

export interface ChosenOffer {
  roomTypeId: string
  ratePlanId: string
  /** Total of the stay (all units), as quoted when chosen. */
  total: string
  depositPercent: string
}

export interface PaymentChoice {
  mode: PaymentMode
  /** API money string ("200000"). */
  amount: string
  method: ManualMethod | ''
  reference: string
  /** Payment link: also email it to the guest. */
  sendEmail: boolean
}

export interface WizardState {
  /** Arrives now: arrival = business date and check-in right after creating it. */
  walkIn: boolean
  checkin: string
  checkout: string
  adults: number
  children: number
  childrenAges: (number | null)[]
  promoCode: string
  /** Quote without IVA (foreign non-resident guest). */
  foreign: boolean
  offer: ChosenOffer | null
  /** Room (and its category) picked on the calendar or the rack. */
  roomId: string | null
  roomTypeId: string | null
  guest: GuestPickerValue | null
  source: BookingSource
  language: 'es' | 'en'
  eta: string
  specialRequests: string
  notes: string
  /** extra id → quantity. */
  extras: Record<string, number>
  payment: PaymentChoice
  status: 'confirmed' | 'tentative'
}

export type StepErrors = Partial<
  Record<'dates' | 'adults' | 'childrenAges' | 'offer' | 'guest' | 'extras' | 'eta' | 'amount' | 'method', string>
>

/** A tentative booking made at the desk keeps its rooms for a day while the guest pays. */
export const TENTATIVE_HOLD_MINUTES = 24 * 60

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/
const ETA = /^([01]\d|2[0-3]):[0-5]\d$/

function isDay(value: string | null): value is string {
  if (!value || !ISO_DAY.test(value)) return false
  return isValid(parse(value, 'yyyy-MM-dd', new Date()))
}

function nextDay(day: string): string {
  return toISODate(addDays(parse(day, 'yyyy-MM-dd', new Date()), 1))
}

function count(value: string | null, fallback: number): number {
  const n = Number(value)
  return value !== null && Number.isInteger(n) && n >= 0 ? n : fallback
}

/** Starting point from the URL (`?checkin&checkout&room_id&room_type_id&adults&walk_in=1`). */
export function initialWizardState(search: URLSearchParams, bd: string): WizardState {
  const walkIn = search.get('walk_in') === '1'
  const checkinParam = search.get('checkin')
  const checkin = walkIn || !isDay(checkinParam) ? bd : checkinParam
  const checkoutParam = search.get('checkout')
  const checkout = isDay(checkoutParam) && checkoutParam > checkin ? checkoutParam : nextDay(checkin)
  return {
    walkIn,
    checkin,
    checkout,
    adults: Math.max(1, count(search.get('adults'), 2)),
    children: 0,
    childrenAges: [],
    promoCode: '',
    foreign: false,
    offer: null,
    roomId: search.get('room_id') || null,
    roomTypeId: search.get('room_type_id') || null,
    guest: null,
    source: 'front_desk',
    language: 'es',
    eta: '',
    specialRequests: '',
    notes: '',
    extras: {},
    payment: { mode: 'none', amount: '', method: '', reference: '', sendEmail: true },
    status: 'confirmed',
  }
}

function positive(amount: string): boolean {
  const n = Number(amount)
  return amount.trim() !== '' && Number.isFinite(n) && n > 0
}

/** Errors of one step, as i18n keys of the `frontdesk` namespace (empty object = the step is complete). */
export function validateStep(step: WizardStep, state: WizardState, bd: string): StepErrors {
  const errors: StepErrors = {}
  switch (step) {
    case 0: {
      if (!isDay(state.checkin) || !isDay(state.checkout)) errors.dates = 'wizard.errors.datesRequired'
      else if (state.walkIn && state.checkin !== bd) errors.dates = 'wizard.errors.walkInToday'
      else if (state.checkin < bd) errors.dates = 'wizard.errors.checkinPast'
      else if (state.checkout <= state.checkin) errors.dates = 'wizard.errors.checkoutAfterCheckin'
      if (state.adults < 1) errors.adults = 'wizard.errors.adultsMin'
      const ages = state.childrenAges.slice(0, state.children)
      if (ages.length < state.children || ages.some((age) => age === null || age < 0)) {
        errors.childrenAges = 'wizard.errors.childAge'
      }
      break
    }
    case 1:
      if (!state.offer) errors.offer = 'wizard.errors.offerRequired'
      break
    case 2:
      if (!state.guest) errors.guest = 'wizard.errors.guestRequired'
      else if (!isExistingGuest(state.guest) && (!state.guest.first_name.trim() || !state.guest.last_name.trim())) {
        errors.guest = 'wizard.errors.guestName'
      }
      break
    case 3:
      if (Object.values(state.extras).some((qty) => !Number.isInteger(qty) || qty < 0)) {
        errors.extras = 'wizard.errors.extraQuantity'
      }
      if (state.eta && !ETA.test(state.eta)) errors.eta = 'wizard.errors.etaInvalid'
      break
    case 4:
      if (state.payment.mode !== 'none' && !positive(state.payment.amount)) errors.amount = 'wizard.errors.amountRequired'
      if (state.payment.mode === 'payment' && !state.payment.method) errors.method = 'wizard.errors.methodRequired'
      break
  }
  return errors
}

/** The first step that is not complete, or null when the reservation can be created. */
export function firstInvalidStep(state: WizardState, bd: string): WizardStep | null {
  for (const step of [0, 1, 2, 3, 4] as WizardStep[]) {
    if (Object.keys(validateStep(step, state, bd)).length > 0) return step
  }
  return null
}

/** Default quantity of an extra (same rule as the folio's "agregar extra": stay · night · person · person-night). */
export function defaultExtraQuantity(chargeType: ExtraChargeType, nights: number, persons: number): number {
  switch (chargeType) {
    case 'per_stay':
      return 1
    case 'per_night':
      return nights
    case 'per_person':
      return persons
    case 'per_person_night':
      return persons * nights
  }
}

/**
 * Whether the booker is quoted without lodging IVA (foreign non-resident, ET art. 481), or null while it
 * can't be told (no guest yet, or a new guest without nationality). The backend applies the same rule
 * when it saves the reservation, so the wizard must quote with it to show the real total.
 */
export function bookerIsForeignNonResident(guest: GuestPickerValue | null): boolean | null {
  if (!guest) return null
  if (isExistingGuest(guest)) return guest.is_foreign_non_resident
  const nationality = (guest.nationality ?? '').toUpperCase()
  if (!nationality) return null
  const residence = (guest.country_of_residence || nationality).toUpperCase()
  return nationality !== 'CO' && residence !== 'CO'
}

/** Query of `GET /bookings/offers/` for the wizard's dates and guests. */
export function offerQuery(state: WizardState): OfferQuery {
  return {
    checkin: state.checkin,
    checkout: state.checkout,
    adults: state.adults,
    children: state.children,
    childrenAges: state.childrenAges.slice(0, state.children).map((age) => age ?? 0),
    promoCode: state.promoCode,
    foreign: state.foreign,
  }
}

/** What to charge by default: the plan's deposit, else the whole stay (whole pesos for COP). */
export function suggestedAmount(state: WizardState, currency: string): string {
  if (!state.offer) return ''
  const total = Number(state.offer.total)
  const deposit = Number(state.offer.depositPercent)
  const amount = deposit > 0 ? (total * deposit) / 100 : total
  return amount.toFixed(currency === 'COP' ? 0 : 2)
}

/** Body of `POST /bookings/reservations/` (the extras and the payment are posted to the folio afterwards). */
export function buildReservationPayload(state: WizardState): ReservationCreateInput {
  const offer = state.offer
  if (!offer || !state.guest) throw new Error('The wizard is not complete')
  const stay: StayRequestInput = {
    room_type_id: offer.roomTypeId,
    rate_plan_id: offer.ratePlanId,
    checkin: state.checkin,
    checkout: state.checkout,
    adults: state.adults,
    children: state.children,
    children_ages: state.childrenAges.slice(0, state.children).map((age) => age ?? 0),
  }
  const roomFits = !state.roomTypeId || state.roomTypeId === offer.roomTypeId
  if (state.roomId && roomFits) stay.room_id = state.roomId
  const payload: ReservationCreateInput = {
    ...(isExistingGuest(state.guest) ? { booker_id: state.guest.id } : { booker: state.guest }),
    stays: [stay],
    source: state.walkIn ? 'walk_in' : state.source,
    notes: state.notes.trim(),
    special_requests: state.specialRequests.trim(),
    promo_code: state.promoCode.trim().toUpperCase(),
    language: state.language,
    eta: state.eta || null,
    status: state.status,
    guarantee: state.payment.mode === 'payment' ? 'deposit' : 'none',
  }
  if (state.status === 'tentative') payload.hold_minutes = TENTATIVE_HOLD_MINUTES
  return payload
}
