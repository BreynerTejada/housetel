import { addDays, isValid, parse } from 'date-fns'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { toISODate } from '@/lib/format'
import type {
  ReservationCreateInput,
  ReservationSource,
  RoomKind,
  RoomOffer,
  RoomOffersQuery,
  StayQuoteLine,
  StayRequestInput,
  StaysQuoteInput,
} from '../api'

/**
 * The new-reservation wizard (plan C1, multi-room since pilot P3): five steps over one state object —
 * 0 dates & guests (and group) · 1 rooms & rates · 2 guest · 3 extras & notes · 4 guarantee & payment.
 * Step 1 picks how many rooms of each offer (dorms: beds), mixing categories, and splits the party between
 * them; the payload sends one `StayRequest` per room (or bed). Pure helpers (validation per step, the split,
 * the payload of `POST /bookings/reservations/`) so they are tested alone.
 */
export const WIZARD_STEPS = ['dates', 'offer', 'guest', 'extras', 'payment'] as const
export type WizardStep = 0 | 1 | 2 | 3 | 4

export type PaymentMode = 'none' | 'payment' | 'link'
export type ManualMethod = 'cash' | 'card_terminal' | 'bank_transfer' | 'other'
export type BookingSource = Extract<ReservationSource, 'front_desk' | 'phone' | 'email'>
export type ExtraChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'

export interface PaymentChoice {
  mode: PaymentMode
  /** API money string ("200000"). */
  amount: string
  method: ManualMethod | ''
  reference: string
  /** Payment link: also email it to the guest. */
  sendEmail: boolean
}

/** Guests of one room (a dorm bed holds exactly one). */
export interface RoomSplit {
  adults: number
  children: number
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
  /** Rooms picked per offer (`offerKey`) → how many (dorm: beds). */
  selection: Record<string, number>
  /** The guests of each room when the desk changed the automatic split (null = automatic). */
  split: RoomSplit[] | null
  /** Room (and its category) picked on the calendar or the rack. */
  roomId: string | null
  roomTypeId: string | null
  /** "Reserva de grupo": a new group with `groupName`… */
  groupMode: boolean
  groupName: string
  /** …or an existing group (the group page opens the wizard with `?group=<id>`). */
  groupId: string | null
  /**
   * A pickup from this group allotment (`?block=<id>`, from the group page): the offers are only its category
   * (with what the block still holds) and every room is sent with `group_block_id`.
   */
  blockId: string | null
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
  Record<
    'dates' | 'adults' | 'childrenAges' | 'group' | 'offer' | 'split' | 'guest' | 'extras' | 'eta' | 'amount' | 'method',
    string
  >
>

/** One room (or dorm bed) being booked. */
export interface RoomUnit {
  key: string
  offerKey: string
  roomTypeId: string
  ratePlanId: string
  kind: RoomKind
  maxAdults: number
  maxChildren: number
  maxOccupancy: number
  baseOccupancy: number
}

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

/**
 * Starting point from the URL (`?checkin&checkout&room_id&room_type_id&adults&walk_in=1&group=<id>&block=<id>&group_mode=1`).
 */
export function initialWizardState(search: URLSearchParams, bd: string): WizardState {
  const walkIn = search.get('walk_in') === '1'
  const checkinParam = search.get('checkin')
  const checkin = walkIn || !isDay(checkinParam) ? bd : checkinParam
  const checkoutParam = search.get('checkout')
  const checkout = isDay(checkoutParam) && checkoutParam > checkin ? checkoutParam : nextDay(checkin)
  const groupId = search.get('group') || null
  const blockId = search.get('block') || null
  return {
    walkIn,
    checkin,
    checkout,
    adults: Math.max(1, count(search.get('adults'), 2)),
    children: 0,
    childrenAges: [],
    promoCode: '',
    foreign: false,
    selection: {},
    split: null,
    roomId: search.get('room_id') || null,
    roomTypeId: search.get('room_type_id') || null,
    groupMode: Boolean(groupId) || search.get('group_mode') === '1',
    groupName: '',
    groupId,
    blockId,
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

// ---- rooms and the split of the party -------------------------------------------------------------------

export const offerKey = (roomTypeId: string, ratePlanId: string) => `${roomTypeId}:${ratePlanId}`

/** How many rooms (beds) are picked in total. */
export function selectedCount(selection: Record<string, number>): number {
  return Object.values(selection).reduce((sum, value) => sum + Math.max(0, value), 0)
}

/** Picked units per category (plans of one category share its availability). */
export function selectedByRoomType(selection: Record<string, number>): Map<string, number> {
  const byType = new Map<string, number>()
  for (const [key, value] of Object.entries(selection)) {
    if (value <= 0) continue
    const roomTypeId = key.split(':')[0]!
    byType.set(roomTypeId, (byType.get(roomTypeId) ?? 0) + value)
  }
  return byType
}

/** The rooms of the selection, in the order of the offers (so the split and the summary are stable). */
export function expandSelection(selection: Record<string, number>, offers: RoomOffer[] | undefined): RoomUnit[] {
  if (!offers) return []
  const units: RoomUnit[] = []
  for (const offer of offers) {
    const key = offerKey(offer.room_type_id, offer.rate_plan_id)
    const quantity = Math.max(0, selection[key] ?? 0)
    for (let index = 0; index < quantity; index += 1) {
      units.push({
        key: `${key}#${index}`,
        offerKey: key,
        roomTypeId: offer.room_type_id,
        ratePlanId: offer.rate_plan_id,
        kind: offer.room_type.kind,
        maxAdults: offer.room_type.max_adults,
        maxChildren: offer.room_type.max_children,
        maxOccupancy: offer.room_type.max_occupancy,
        baseOccupancy: offer.room_type.base_occupancy || 1,
      })
    }
  }
  return units
}

/** Guests a room can still take (adults / children) with this split. */
function roomFor(unit: RoomUnit, split: RoomSplit) {
  if (unit.kind === 'dorm') return { adults: 0, children: 0 }
  const seats = unit.maxOccupancy - split.adults - split.children
  return {
    adults: Math.max(0, Math.min(unit.maxAdults - split.adults, seats)),
    children: Math.max(0, Math.min(unit.maxChildren - split.children, seats)),
  }
}

/**
 * The automatic split: every room gets one adult first (a private room needs one; a dorm bed holds one guest,
 * a child when the dorm admits children and the adults ran out); then the other adults go round-robin to the
 * rooms up to their standard occupancy, then up to their maximum; then the children. `leftover` = the guests
 * who don't fit (more rooms are needed).
 */
export function autoSplit(units: RoomUnit[], adults: number, children: number) {
  const split: RoomSplit[] = units.map(() => ({ adults: 0, children: 0 }))
  let restAdults = adults
  let restChildren = children
  units.forEach((unit, index) => {
    if (restAdults > 0) {
      split[index]!.adults = 1
      restAdults -= 1
    } else if (unit.kind === 'dorm' && restChildren > 0 && unit.maxChildren > 0) {
      split[index]!.children = 1
      restChildren -= 1
    }
  })
  for (const cap of ['base', 'max'] as const) {
    let placed = true
    while (restAdults > 0 && placed) {
      placed = false
      units.forEach((unit, index) => {
        const current = split[index]!
        const room = roomFor(unit, current)
        const limit = cap === 'base' ? Math.min(unit.baseOccupancy, unit.maxAdults) : unit.maxAdults
        if (restAdults > 0 && room.adults > 0 && current.adults < limit) {
          current.adults += 1
          restAdults -= 1
          placed = true
        }
      })
    }
  }
  let placed = true
  while (restChildren > 0 && placed) {
    placed = false
    units.forEach((unit, index) => {
      const current = split[index]!
      if (restChildren > 0 && current.adults > 0 && roomFor(unit, current).children > 0) {
        current.children += 1
        restChildren -= 1
        placed = true
      }
    })
  }
  return { split, leftover: { adults: restAdults, children: restChildren } }
}

/** The split in use: the desk's own while it matches the rooms, else the automatic one. */
export function roomSplit(state: WizardState, units: RoomUnit[]): { split: RoomSplit[]; auto: boolean } {
  if (state.split && state.split.length === units.length) return { split: state.split, auto: false }
  return { split: autoSplit(units, state.adults, state.children).split, auto: true }
}

/** Why a split can't be booked (an i18n key of the `frontdesk` namespace), or null. */
export function splitProblem(units: RoomUnit[], split: RoomSplit[], adults: number, children: number): string | null {
  for (const [index, unit] of units.entries()) {
    const room = split[index]
    if (!room) return 'wizard.errors.splitTotals'
    if (unit.kind === 'dorm') {
      if (room.adults + room.children !== 1 || (room.children > 0 && unit.maxChildren === 0)) return 'wizard.errors.splitCapacity'
      continue
    }
    if (room.adults < 1) return 'wizard.errors.roomWithoutAdult'
    if (room.adults > unit.maxAdults || room.children > unit.maxChildren || room.adults + room.children > unit.maxOccupancy) {
      return 'wizard.errors.splitCapacity'
    }
  }
  const sumAdults = split.reduce((sum, room) => sum + room.adults, 0)
  const sumChildren = split.reduce((sum, room) => sum + room.children, 0)
  if (sumAdults !== adults || sumChildren !== children) return 'wizard.errors.splitTotals'
  return null
}

/** The quote line of this room, only while it still matches it (a stale quote shows no price). */
export function matchingLine(lines: StayQuoteLine[] | undefined, index: number, unit: RoomUnit, room: RoomSplit) {
  const line = lines?.find((item) => item.index === index)
  if (!line) return undefined
  const same =
    line.room_type_id === unit.roomTypeId &&
    line.rate_plan_id === unit.ratePlanId &&
    line.adults === room.adults &&
    line.children === room.children
  return same ? line : undefined
}

/** How many guests the picked rooms hold at most (dorm beds: one). */
export function capacityOf(units: RoomUnit[]): number {
  return units.reduce((sum, unit) => sum + (unit.kind === 'dorm' ? 1 : unit.maxOccupancy), 0)
}

// ---- validation ------------------------------------------------------------------------------------------

/**
 * Errors of one step, as i18n keys of the `frontdesk` namespace (empty object = the step is complete). Step 1
 * needs the room offers to check availability and the split; without them only "nothing picked" is known.
 */
export function validateStep(step: WizardStep, state: WizardState, bd: string, offers?: RoomOffer[]): StepErrors {
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
      if (state.groupMode && !state.groupId && !state.groupName.trim()) errors.group = 'wizard.errors.groupName'
      break
    }
    case 1: {
      if (selectedCount(state.selection) === 0) {
        errors.offer = 'wizard.errors.offerRequired'
        break
      }
      if (!offers) break
      const units = expandSelection(state.selection, offers)
      if (units.length === 0) {
        errors.offer = 'wizard.errors.offerRequired'
        break
      }
      for (const [roomTypeId, picked] of selectedByRoomType(state.selection)) {
        const offer = offers.find((item) => item.room_type_id === roomTypeId)
        if (!offer || picked > offer.available_units) errors.offer = 'wizard.errors.notEnoughRooms'
      }
      const { split, auto } = roomSplit(state, units)
      const problem = splitProblem(units, split, state.adults, state.children)
      if (problem) errors.split = auto && problem === 'wizard.errors.splitTotals' ? 'wizard.errors.guestsDontFit' : problem
      break
    }
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

function positive(amount: string): boolean {
  const n = Number(amount)
  return amount.trim() !== '' && Number.isFinite(n) && n > 0
}

/** The first step that is not complete, or null when the reservation can be created. */
export function firstInvalidStep(state: WizardState, bd: string, offers?: RoomOffer[]): WizardStep | null {
  for (const step of [0, 1, 2, 3, 4] as WizardStep[]) {
    if (Object.keys(validateStep(step, state, bd, offers)).length > 0) return step
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

// ---- API shapes ------------------------------------------------------------------------------------------

/** Query of `GET /bookings/room-offers/` for the wizard's dates. */
export function roomOffersQuery(state: WizardState): RoomOffersQuery {
  return { checkin: state.checkin, checkout: state.checkout, promoCode: state.promoCode, foreign: state.foreign, block: state.blockId }
}

/** One `StayRequest` per room (bed), with its guests and the ages of its children in order. */
export function buildStays(state: WizardState, units: RoomUnit[], split: RoomSplit[]): StayRequestInput[] {
  const ages = state.childrenAges.slice(0, state.children).map((age) => age ?? 0)
  let nextAge = 0
  let roomUsed = false
  return units.map((unit, index) => {
    const room = split[index] ?? { adults: 1, children: 0 }
    const stay: StayRequestInput = {
      room_type_id: unit.roomTypeId,
      rate_plan_id: unit.ratePlanId,
      checkin: state.checkin,
      checkout: state.checkout,
      adults: room.adults,
      children: room.children,
      children_ages: ages.slice(nextAge, nextAge + room.children),
    }
    // A pickup from the allotment: the offers were only its category, so every room comes from it.
    if (state.blockId) stay.group_block_id = state.blockId
    nextAge += room.children
    // The room picked on the rack or the calendar: the first room of its category (every bed of a dorm).
    const fits = !state.roomTypeId || state.roomTypeId === unit.roomTypeId
    if (state.roomId && fits && (unit.kind === 'dorm' || !roomUsed)) {
      stay.room_id = state.roomId
      roomUsed = true
    }
    return stay
  })
}

/** Body of `POST /bookings/reservations/quote/` for the rooms picked (null while the split is not valid). */
export function quoteInput(state: WizardState, offers: RoomOffer[] | undefined): StaysQuoteInput | null {
  const units = expandSelection(state.selection, offers)
  if (units.length === 0) return null
  const { split } = roomSplit(state, units)
  if (splitProblem(units, split, state.adults, state.children)) return null
  return { stays: buildStays(state, units, split), promo_code: state.promoCode.trim().toUpperCase(), foreign: state.foreign }
}

/**
 * What to charge by default: per room its plan's deposit, else the whole room (whole pesos for COP); '' while
 * the rooms are not priced yet.
 */
export function suggestedAmount(lines: StayQuoteLine[] | undefined, offers: RoomOffer[] | undefined, currency: string): string {
  if (!lines?.length) return ''
  const amount = lines.reduce((sum, line) => {
    const offer = offers?.find((item) => item.room_type_id === line.room_type_id && item.rate_plan_id === line.rate_plan_id)
    const deposit = Number(offer?.rate_plan.deposit_percent ?? 0)
    return sum + (deposit > 0 ? (Number(line.total) * deposit) / 100 : Number(line.total))
  }, 0)
  return amount.toFixed(currency === 'COP' ? 0 : 2)
}

/** The deposit % every picked plan asks for (null when none asks, `'mixed'` when they differ). */
export function depositPercent(units: RoomUnit[], offers: RoomOffer[] | undefined): number | 'mixed' | null {
  const values = new Set(
    units.map((unit) => Number(offers?.find((offer) => offerKey(offer.room_type_id, offer.rate_plan_id) === unit.offerKey)?.rate_plan.deposit_percent ?? 0)),
  )
  if (values.size === 0 || (values.size === 1 && values.has(0))) return null
  if (values.size > 1) return 'mixed'
  return [...values][0]!
}

/** Body of `POST /bookings/reservations/` (the extras and the payment are posted to the folio afterwards). */
export function buildReservationPayload(state: WizardState, offers: RoomOffer[] | undefined): ReservationCreateInput {
  const units = expandSelection(state.selection, offers)
  if (units.length === 0 || !state.guest) throw new Error('The wizard is not complete')
  const { split } = roomSplit(state, units)
  const payload: ReservationCreateInput = {
    ...(isExistingGuest(state.guest) ? { booker_id: state.guest.id } : { booker: state.guest }),
    stays: buildStays(state, units, split),
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
  if (state.groupId) payload.group_id = state.groupId
  else if (state.groupMode && state.groupName.trim()) payload.group_name = state.groupName.trim()
  // The group's rooms were already agreed: a pickup from its allotment skips the rate restrictions (min LOS…).
  if (state.blockId) payload.enforce_restrictions = false
  return payload
}
