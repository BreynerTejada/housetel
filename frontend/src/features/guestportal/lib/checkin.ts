import type { CheckinPayload, CheckinSlot, CheckinStep, DocumentKind, GuestEntry, MissingItem } from '../api'

/**
 * Pure rules of the online check-in stepper (Huéspedes → Documentos → Llegada → Firma y términos →
 * Pago → Listo). The backend is the source of truth (it validates again and says what is `missing`); these
 * helpers decide what to show and catch the obvious mistakes before a round trip.
 */

export const ALL_STEPS: CheckinStep[] = ['guests', 'documents', 'arrival', 'signature', 'payment', 'done']

/** Document types a guest can register with (Guest.DocumentType without NIT, which is not a person's ID). */
export const DOCUMENT_TYPES = ['CC', 'CE', 'TI', 'PA', 'PPT', 'PEP', 'DNI', 'OTHER'] as const

export const IDENTITY_FIELDS = [
  'first_name',
  'last_name',
  'document_type',
  'document_number',
  'nationality',
  'country_of_residence',
  'birth_date',
] as const
export const TRAVEL_FIELDS = ['travel_reason', 'origin', 'destination'] as const

export function owes(checkin: Pick<CheckinPayload, 'balance'>): boolean {
  return Number(checkin.balance.due) > 0 && checkin.balance.can_pay
}

/** Steps shown for this check-in: documents only if the hotel asks for them, payment only if something is owed. */
export function stepsFor(checkin: CheckinPayload): CheckinStep[] {
  return ALL_STEPS.filter((step) => {
    if (step === 'documents') return checkin.settings.require_document_photo
    if (step === 'payment') return owes(checkin)
    return true
  })
}

function stepOfMissing(missing: MissingItem[]): CheckinStep {
  if (missing.some((item) => item.code === 'guest_data')) return 'guests'
  if (missing.some((item) => item.code === 'document')) return 'documents'
  return 'signature'
}

/** Where the stepper opens: the saved step, the first gap of an unfinished one, or payment/done once completed. */
export function resolveStep(checkin: CheckinPayload): CheckinStep {
  const visible = stepsFor(checkin)
  if (checkin.status === 'completed') return owes(checkin) ? 'payment' : 'done'
  let step = checkin.current_step
  if (step === 'payment' || step === 'done') step = stepOfMissing(checkin.missing)
  if (visible.includes(step)) return step
  // a hidden step (documents not required): the next visible one
  return ALL_STEPS.slice(ALL_STEPS.indexOf(step)).find((candidate) => visible.includes(candidate)) ?? 'guests'
}

// ---- Guests step ----------------------------------------------------------------------------------

export interface GuestForm {
  slot: number
  stay_id: string
  role: 'booker' | 'companion'
  guest_id: string | null
  /** A companion the hotel registered: the portal shows only the name and a masked document. */
  known: boolean
  /** Keep that companion as the hotel has it (sent as `keep: true`, nothing rewritten). */
  keep: boolean
  /** The booking holds this place for a child (no document photo is asked for minors). */
  child: boolean
  document_hint: string
  first_name: string
  last_name: string
  document_type: string
  document_number: string
  nationality: string
  country_of_residence: string
  city_of_residence: string
  birth_date: string
  email: string
  phone: string
  travel_reason: string
  origin: string
  destination: string
}

export interface GuestFormValues {
  guests: GuestForm[]
}

export function guestFormsFrom(checkin: CheckinPayload): GuestForm[] {
  const booker = checkin.guests.find((slot) => slot.role === 'booker')?.data ?? {}
  return checkin.guests.map((slot) => {
    const data = slot.data
    const known = slot.role === 'companion' && Boolean(slot.guest_id)
    const base: GuestForm = {
      slot: slot.slot,
      stay_id: slot.stay_id,
      role: slot.role,
      guest_id: slot.guest_id,
      known,
      keep: known && slot.complete,
      child: slot.role === 'companion' && slot.expected === 'child',
      document_hint: data.document_hint ?? '',
      first_name: data.first_name ?? '',
      last_name: data.last_name ?? '',
      document_type: data.document_type ?? '',
      document_number: data.document_number ?? '',
      nationality: data.nationality ?? '',
      country_of_residence: data.country_of_residence ?? '',
      city_of_residence: data.city_of_residence ?? '',
      birth_date: data.birth_date ?? '',
      email: data.email ?? '',
      phone: data.phone ?? '',
      travel_reason: slot.travel.travel_reason ?? '',
      origin: slot.travel.origin ?? '',
      destination: slot.travel.destination ?? '',
    }
    if (slot.role === 'booker') {
      base.travel_reason ||= 'leisure'
      base.origin ||= data.city_of_residence ?? ''
      base.destination ||= checkin.property.city
    } else if (!slot.guest_id) {
      // families and friends usually share the booker's origin: prefilled, editable
      base.nationality = booker.nationality ?? ''
      base.country_of_residence = booker.country_of_residence ?? ''
      base.city_of_residence = booker.city_of_residence ?? ''
      const colombian = booker.nationality === 'CO'
      base.document_type = booker.nationality ? (colombian ? (base.child ? 'TI' : 'CC') : 'PA') : ''
    }
    return base
  })
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** Errors keyed like the backend's `fields` (`guests.<index>.<field>`), as i18n keys. */
export function validateGuests(forms: GuestForm[], today: string): Record<string, string> {
  const errors: Record<string, string> = {}
  forms.forEach((form, index) => {
    if (form.keep) return
    const key = (field: string) => `guests.${index}.${field}`
    for (const field of IDENTITY_FIELDS) {
      if (!form[field].trim()) errors[key(field)] = 'validation.required'
    }
    if (form.birth_date && form.birth_date > today) errors[key('birth_date')] = 'guestportal:checkin.errors.birthFuture'
    if (form.email.trim() && !EMAIL.test(form.email.trim())) errors[key('email')] = 'validation.email'
    if (form.role === 'booker') {
      for (const field of TRAVEL_FIELDS) {
        if (!form[field].trim()) errors[key(field)] = 'validation.required'
      }
    }
  })
  return errors
}

export function guestEntries(forms: GuestForm[]): GuestEntry[] {
  return forms.map((form) => {
    if (form.keep) return { stay_id: form.stay_id, role: form.role, guest_id: form.guest_id, keep: true }
    const entry: GuestEntry = {
      stay_id: form.stay_id,
      role: form.role,
      guest_id: form.guest_id,
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      document_type: form.document_type,
      document_number: form.document_number.trim(),
      nationality: form.nationality,
      country_of_residence: form.country_of_residence,
      city_of_residence: form.city_of_residence.trim(),
      birth_date: form.birth_date || null,
      email: form.email.trim(),
      phone: form.phone.trim(),
    }
    if (form.role === 'booker') {
      entry.travel_reason = form.travel_reason
      entry.origin = form.origin.trim()
      entry.destination = form.destination.trim()
    }
    return entry
  })
}

// ---- Documents step -------------------------------------------------------------------------------

export function documentKindFor(documentType: string | undefined): DocumentKind {
  return documentType === 'PA' ? 'passport' : 'id_front'
}

export function identityDocuments(slot: CheckinSlot) {
  return slot.documents.filter((document) => document.kind !== 'signature')
}

/** Adults registered on the booking who still have no identity document. */
export function guestsNeedingDocuments(checkin: CheckinPayload): CheckinSlot[] {
  return checkin.guests.filter((slot) => slot.guest_id && slot.is_adult && identityDocuments(slot).length === 0)
}

export function slotName(slot: CheckinSlot): string {
  return [slot.data.first_name, slot.data.last_name].filter(Boolean).join(' ')
}
