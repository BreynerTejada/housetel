import { describe, expect, it } from 'vitest'
import {
  documentKindFor,
  guestEntries,
  guestFormsFrom,
  guestsNeedingDocuments,
  resolveStep,
  stepsFor,
  validateGuests,
} from '../lib/checkin'
import { makeCheckin, registeredCheckin } from './fixtures'

describe('stepsFor', () => {
  it('lists every step when the hotel asks for documents and there is a balance to pay', () => {
    expect(stepsFor(makeCheckin())).toEqual(['guests', 'documents', 'arrival', 'signature', 'payment', 'done'])
  })

  it('skips documents when the hotel does not ask for them, and payment when nothing is owed', () => {
    const checkin = makeCheckin({
      settings: { require_document_photo: false, require_signature: true },
      balance: { total: '761600.00', paid: '761600.00', due: '0.00', currency: 'COP', can_pay: false },
    })

    expect(stepsFor(checkin)).toEqual(['guests', 'arrival', 'signature', 'done'])
  })
})

describe('resolveStep', () => {
  it('opens a fresh check-in at the guests step and resumes a started one where it was left', () => {
    expect(resolveStep(makeCheckin())).toBe('guests')
    expect(resolveStep(registeredCheckin({ current_step: 'arrival' }))).toBe('arrival')
  })

  it('goes to payment after completing while something is owed, otherwise to done', () => {
    const completed = registeredCheckin({ status: 'completed', current_step: 'payment', missing: [] })
    expect(resolveStep(completed)).toBe('payment')

    const paid = { ...completed, balance: { ...completed.balance, due: '0.00', can_pay: false } }
    expect(resolveStep(paid)).toBe('done')
  })

  it('sends an unfinished check-in that already passed the signature back to what is missing', () => {
    const stuck = registeredCheckin({ current_step: 'payment', missing: [{ code: 'document', guest_id: 'guest-ana' }] })

    expect(resolveStep(stuck)).toBe('documents')
  })

  it('moves past a hidden documents step', () => {
    const checkin = registeredCheckin({ settings: { require_document_photo: false, require_signature: true } })

    expect(resolveStep(checkin)).toBe('arrival')
  })
})

describe('guest forms', () => {
  it('prefills the booker and starts companions with the booker origin', () => {
    const [booker, companion] = guestFormsFrom(makeCheckin())

    expect(booker).toMatchObject({ role: 'booker', first_name: 'Laura', document_number: '52123456', destination: 'Cartagena', origin: 'Bogotá' })
    expect(companion).toMatchObject({
      role: 'companion',
      guest_id: null,
      first_name: '',
      nationality: 'CO',
      country_of_residence: 'CO',
      keep: false,
    })
  })

  it('keeps a companion the hotel already registered unless the guest edits it', () => {
    const forms = guestFormsFrom(registeredCheckin())

    expect(forms[1]).toMatchObject({ guest_id: 'guest-ana', keep: true, known: true, first_name: 'Ana', document_number: '' })
    expect(guestEntries(forms)[1]).toEqual({ stay_id: 'stay-1', role: 'companion', guest_id: 'guest-ana', keep: true })
  })

  it('requires the identity data of every guest and the travel data of the booker', () => {
    const forms = guestFormsFrom(makeCheckin())
    forms[0]!.travel_reason = ''

    const errors = validateGuests(forms, '2026-10-01')

    expect(errors['guests.0.birth_date']).toBe('validation.required')
    expect(errors['guests.0.travel_reason']).toBe('validation.required')
    expect(errors['guests.1.first_name']).toBe('validation.required')
    expect(errors['guests.1.document_number']).toBe('validation.required')
    expect(errors['guests.1.travel_reason']).toBeUndefined() // companions travel with the booker
  })

  it('rejects birth dates in the future and malformed emails', () => {
    const forms = guestFormsFrom(makeCheckin())
    forms[0]!.birth_date = '2030-01-01'
    forms[0]!.email = 'laura-at-example'

    const errors = validateGuests(forms, '2026-10-01')

    expect(errors['guests.0.birth_date']).toBe('guestportal:checkin.errors.birthFuture')
    expect(errors['guests.0.email']).toBe('validation.email')
  })

  it('sends trimmed entries with the role, the stay and the guest ids', () => {
    const forms = guestFormsFrom(makeCheckin())
    forms[0]!.birth_date = '1990-04-02'
    Object.assign(forms[1]!, { first_name: ' Ana ', last_name: 'Pérez', document_type: 'CC', document_number: '1020304050', birth_date: '1992-06-15' })

    const [booker, companion] = guestEntries(forms)

    expect(booker).toMatchObject({ role: 'booker', guest_id: 'guest-booker', birth_date: '1990-04-02', travel_reason: 'leisure' })
    expect(companion).toMatchObject({ role: 'companion', guest_id: null, first_name: 'Ana', document_number: '1020304050' })
    expect(companion).not.toHaveProperty('keep')
  })
})

describe('documents', () => {
  it('asks a passport page from passport holders and the front of the ID from everyone else', () => {
    expect(documentKindFor('PA')).toBe('passport')
    expect(documentKindFor('CC')).toBe('id_front')
  })

  it('lists the adults without an identity document', () => {
    const checkin = registeredCheckin()
    checkin.guests[0]!.documents = [{ id: 'd1', kind: 'id_front', uploaded_via: 'portal', created_at: '2026-10-01T10:00:00-05:00' }]

    expect(guestsNeedingDocuments(checkin).map((slot) => slot.guest_id)).toEqual(['guest-ana'])
  })
})
