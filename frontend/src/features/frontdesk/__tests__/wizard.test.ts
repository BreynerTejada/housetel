import { describe, expect, it } from 'vitest'
import {
  buildReservationPayload,
  defaultExtraQuantity,
  firstInvalidStep,
  initialWizardState,
  validateStep,
  type WizardState,
} from '../lib/wizard'

const BD = '2026-10-01'

function state(overrides: Partial<WizardState> = {}): WizardState {
  return { ...initialWizardState(new URLSearchParams(), BD), ...overrides }
}

const offer = { roomTypeId: 'rt-dbl', ratePlanId: 'plan-flex', total: '761600.00', depositPercent: '0.00' }
const existingGuest = {
  id: 'guest-1',
  first_name: 'Laura',
  last_name: 'Gómez',
  full_name: 'Laura Gómez',
  email: 'laura@example.com',
  phone: '+573001234567',
  document_type: 'CC' as const,
  document_number: '52123456',
  nationality: 'CO',
  country_of_residence: 'CO',
  city_of_residence: 'Cartagena',
  language: 'es',
  is_vip: false,
  blacklisted: false,
  tags: [],
  is_foreign_non_resident: false,
  anonymized_at: null,
  stays_count: 2,
  reservations_count: 2,
  last_stay_date: null,
  created_at: '2026-09-01T10:00:00-05:00',
}

describe('initialWizardState', () => {
  it('starts tonight for one night with two adults', () => {
    const initial = initialWizardState(new URLSearchParams(), BD)

    expect(initial).toMatchObject({ walkIn: false, checkin: BD, checkout: '2026-10-02', adults: 2, children: 0 })
    expect(initial.offer).toBeNull()
    expect(initial.guest).toBeNull()
  })

  it('takes the dates, room and category the calendar sends', () => {
    const initial = initialWizardState(
      new URLSearchParams('checkin=2026-10-05&checkout=2026-10-08&room_id=room-203&room_type_id=rt-sup&adults=1'),
      BD,
    )

    expect(initial).toMatchObject({
      checkin: '2026-10-05',
      checkout: '2026-10-08',
      roomId: 'room-203',
      roomTypeId: 'rt-sup',
      adults: 1,
    })
  })

  it('a walk-in always arrives on the business date', () => {
    const staying = initialWizardState(new URLSearchParams('walk_in=1&checkin=2026-10-05&checkout=2026-10-03'), BD)
    const noCheckout = initialWizardState(new URLSearchParams('walk_in=1&checkout=2026-10-01'), BD)

    expect(staying).toMatchObject({ walkIn: true, checkin: BD, checkout: '2026-10-03' })
    expect(noCheckout).toMatchObject({ walkIn: true, checkin: BD, checkout: '2026-10-02' })
  })

  it('ignores dates that are not calendar days', () => {
    const initial = initialWizardState(new URLSearchParams('checkin=mañana&checkout=2026-13-45'), BD)

    expect(initial).toMatchObject({ checkin: BD, checkout: '2026-10-02' })
  })
})

describe('validateStep', () => {
  it('dates: the checkout must come after the arrival', () => {
    expect(validateStep(0, state({ checkin: '2026-10-03', checkout: '2026-10-03' }), BD)).toEqual({
      dates: 'wizard.errors.checkoutAfterCheckin',
    })
    expect(validateStep(0, state({ checkin: '', checkout: '' }), BD)).toEqual({ dates: 'wizard.errors.datesRequired' })
  })

  it('dates: no arrivals before the business date', () => {
    expect(validateStep(0, state({ checkin: '2026-09-30', checkout: '2026-10-02' }), BD)).toEqual({
      dates: 'wizard.errors.checkinPast',
    })
  })

  it('dates: a walk-in arrives today', () => {
    expect(validateStep(0, state({ walkIn: true, checkin: '2026-10-02', checkout: '2026-10-03' }), BD)).toEqual({
      dates: 'wizard.errors.walkInToday',
    })
  })

  it('guests: at least one adult and the age of every child', () => {
    expect(validateStep(0, state({ adults: 0 }), BD)).toEqual({ adults: 'wizard.errors.adultsMin' })
    expect(validateStep(0, state({ children: 2, childrenAges: [7, null] }), BD)).toEqual({
      childrenAges: 'wizard.errors.childAge',
    })
    expect(validateStep(0, state({ children: 2, childrenAges: [7, 3] }), BD)).toEqual({})
  })

  it('rate: an offer must be chosen', () => {
    expect(validateStep(1, state(), BD)).toEqual({ offer: 'wizard.errors.offerRequired' })
    expect(validateStep(1, state({ offer }), BD)).toEqual({})
  })

  it('guest: someone must hold the reservation, with first and last name', () => {
    expect(validateStep(2, state(), BD)).toEqual({ guest: 'wizard.errors.guestRequired' })
    expect(validateStep(2, state({ guest: { first_name: 'Ana', last_name: '' } }), BD)).toEqual({
      guest: 'wizard.errors.guestName',
    })
    expect(validateStep(2, state({ guest: existingGuest }), BD)).toEqual({})
  })

  it('extras and notes: whole quantities and a valid arrival time', () => {
    expect(validateStep(3, state({ extras: { brk: -1 } }), BD)).toEqual({ extras: 'wizard.errors.extraQuantity' })
    expect(validateStep(3, state({ eta: '25:10' }), BD)).toEqual({ eta: 'wizard.errors.etaInvalid' })
    expect(validateStep(3, state({ eta: '21:30', extras: { brk: 4 } }), BD)).toEqual({})
  })

  it('payment: an amount above zero, and a method for payments taken now', () => {
    expect(validateStep(4, state({ payment: { mode: 'payment', amount: '', method: 'card_terminal', reference: '', sendEmail: false } }), BD)).toEqual({
      amount: 'wizard.errors.amountRequired',
    })
    expect(validateStep(4, state({ payment: { mode: 'link', amount: '0', method: '', reference: '', sendEmail: true } }), BD)).toEqual({
      amount: 'wizard.errors.amountRequired',
    })
    expect(validateStep(4, state({ payment: { mode: 'payment', amount: '200000', method: '', reference: '', sendEmail: false } }), BD)).toEqual({
      method: 'wizard.errors.methodRequired',
    })
    expect(validateStep(4, state({ payment: { mode: 'none', amount: '', method: '', reference: '', sendEmail: false } }), BD)).toEqual({})
  })
})

describe('firstInvalidStep', () => {
  it('points at the earliest step that still needs something', () => {
    expect(firstInvalidStep(state({ offer, guest: existingGuest }), BD)).toBeNull()
    expect(firstInvalidStep(state({ offer }), BD)).toBe(2)
    expect(firstInvalidStep(state({ adults: 0, offer, guest: existingGuest }), BD)).toBe(0)
  })
})

describe('defaultExtraQuantity', () => {
  it('follows how the extra is charged', () => {
    expect(defaultExtraQuantity('per_stay', 3, 2)).toBe(1)
    expect(defaultExtraQuantity('per_night', 3, 2)).toBe(3)
    expect(defaultExtraQuantity('per_person', 3, 2)).toBe(2)
    expect(defaultExtraQuantity('per_person_night', 3, 2)).toBe(6)
  })
})

describe('buildReservationPayload', () => {
  it('sends an existing guest by id and the chosen offer as the stay', () => {
    const payload = buildReservationPayload(
      state({
        checkin: '2026-10-01',
        checkout: '2026-10-03',
        adults: 2,
        children: 1,
        childrenAges: [7],
        offer,
        guest: existingGuest,
        source: 'phone',
        eta: '21:30',
        specialRequests: 'Cuna',
        notes: 'Cliente frecuente',
        promoCode: ' bienvenida10 ',
        language: 'es',
      }),
    )

    expect(payload).toEqual({
      booker_id: 'guest-1',
      stays: [
        {
          room_type_id: 'rt-dbl',
          rate_plan_id: 'plan-flex',
          checkin: '2026-10-01',
          checkout: '2026-10-03',
          adults: 2,
          children: 1,
          children_ages: [7],
        },
      ],
      source: 'phone',
      notes: 'Cliente frecuente',
      special_requests: 'Cuna',
      promo_code: 'BIENVENIDA10',
      language: 'es',
      eta: '21:30',
      status: 'confirmed',
      guarantee: 'none',
    })
  })

  it('sends a new guest as data for the backend to create', () => {
    const payload = buildReservationPayload(state({ offer, guest: { first_name: 'Ana', last_name: 'Ruiz', email: 'ana@example.com' } }))

    expect(payload.booker).toEqual({ first_name: 'Ana', last_name: 'Ruiz', email: 'ana@example.com' })
    expect(payload.booker_id).toBeUndefined()
  })

  it('a walk-in is booked as a walk-in', () => {
    expect(buildReservationPayload(state({ walkIn: true, offer, guest: existingGuest, source: 'phone' })).source).toBe('walk_in')
  })

  it('keeps the room picked on the calendar only for its own category', () => {
    const sameCategory = buildReservationPayload(state({ offer, guest: existingGuest, roomId: 'room-101', roomTypeId: 'rt-dbl' }))
    const otherCategory = buildReservationPayload(
      state({ offer: { ...offer, roomTypeId: 'rt-ste' }, guest: existingGuest, roomId: 'room-101', roomTypeId: 'rt-dbl' }),
    )

    expect(sameCategory.stays[0]).toMatchObject({ room_id: 'room-101' })
    expect(otherCategory.stays[0]).not.toHaveProperty('room_id')
  })

  it('a payment taken now is the guarantee; a tentative booking is held for a day', () => {
    const paid = buildReservationPayload(
      state({ offer, guest: existingGuest, payment: { mode: 'payment', amount: '200000', method: 'card_terminal', reference: 'V-1', sendEmail: false } }),
    )
    const held = buildReservationPayload(state({ offer, guest: existingGuest, status: 'tentative' }))

    expect(paid.guarantee).toBe('deposit')
    expect(held).toMatchObject({ status: 'tentative', hold_minutes: 1440 })
  })
})
