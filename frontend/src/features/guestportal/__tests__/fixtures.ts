import type {
  CheckinPayload,
  CheckinSlot,
  PortalProperty,
  PortalReservation,
  PortalStay,
  PortalSummary,
  StaffCheckin,
} from '../api'

export const TOKEN = 'eyJyIjoiOTQ0ZDU1MDQifQ:1tAbCd:sig-portal'

export const property: PortalProperty = {
  name: 'Hotel Casa Aurora',
  slug: 'casa-aurora',
  city: 'Cartagena',
  address: 'Calle del Cuartel #36-77, Centro Histórico',
  phone: '+57 605 660 1234',
  email: 'reservas@casaaurora.co',
  website: 'https://casaaurora.co',
  check_in_time: '15:00',
  check_out_time: '12:00',
  timezone: 'America/Bogota',
  currency: 'COP',
  default_language: 'es',
  primary_color: '#B4583B',
  logo: '',
  photo: null,
  house_rules: { es: 'No se permiten mascotas.', en: 'No pets allowed.' },
}

export const reservation: PortalReservation = {
  code: 'HT-7K2M9Q',
  status: 'confirmed',
  source: 'booking_engine',
  channel_code: '',
  checkin_date: '2026-10-05',
  checkout_date: '2026-10-07',
  nights: 2,
  adults: 2,
  children: 0,
  currency: 'COP',
  total_amount: '761600.00',
  eta: null,
  language: 'es',
  cancelled_at: null,
  cancellation_fee: '0.00',
}

export const stay: PortalStay = {
  id: 'stay-1',
  status: 'confirmed',
  checkin_date: '2026-10-05',
  checkout_date: '2026-10-07',
  nights: 2,
  adults: 2,
  children: 0,
  room_type: { id: 'rt-1', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, kind: 'private', photo: null },
  rate_plan: { id: 'rp-1', code: 'FLEX', name: { es: 'Tarifa flexible', en: 'Flexible rate' }, meal_plan: 'room_only' },
  room: null,
  total_amount: '761600.00',
}

export function makeSummary(overrides: Partial<PortalSummary> = {}): PortalSummary {
  return {
    today: '2026-10-01',
    property,
    reservation,
    stays: [stay],
    guests: [{ id: 'guest-booker', first_name: 'Laura', full_name: 'Laura Gómez', role: 'booker', stay_id: null }],
    balance: { total: '761600.00', paid: '0.00', due: '761600.00', currency: 'COP', can_pay: true },
    payments: [],
    checkin: {
      status: 'not_started',
      current_step: 'guests',
      completed_at: null,
      opens_on: '2026-09-28',
      is_open: true,
      reason: null,
    },
    extras: [
      {
        id: 'extra-brk',
        code: 'BRK',
        name: { es: 'Desayuno', en: 'Breakfast' },
        charge_type: 'per_person_night',
        unit_price: '41650.00',
        default_quantity: 4,
        default_total: '166600.00',
        tax_exempt: false,
        currency: 'COP',
      },
    ],
    requests: [],
    cancellation: {
      can_cancel: true,
      reason: null,
      fee: '0.00',
      fee_reason: 'free_window',
      free_until: '2026-10-03T15:00:00-05:00',
      non_refundable: false,
      policy: { name: { es: 'Flexible 48h', en: 'Flexible 48h' }, description: {} },
      currency: 'COP',
    },
    modification: { can_modify: true, reason: null, free_until: '2026-10-03T15:00:00-05:00', max_nights: 30 },
    settings: { auto_approve_extras: true },
    ...overrides,
  }
}

export const bookerSlot: CheckinSlot = {
  slot: 0,
  stay_id: 'stay-1',
  role: 'booker',
  guest_id: 'guest-booker',
  complete: false,
  is_adult: true,
  data: {
    first_name: 'Laura',
    last_name: 'Gómez',
    document_type: 'CC',
    document_number: '52123456',
    nationality: 'CO',
    country_of_residence: 'CO',
    city_of_residence: 'Bogotá',
    birth_date: null,
    email: 'laura@example.com',
    phone: '+573001234567',
  },
  travel: {},
  documents: [],
}

export const emptyCompanionSlot: CheckinSlot = {
  slot: 1,
  stay_id: 'stay-1',
  role: 'companion',
  guest_id: null,
  complete: false,
  is_adult: true,
  data: {},
  travel: {},
  documents: [],
}

export function makeCheckin(overrides: Partial<CheckinPayload> = {}): CheckinPayload {
  return {
    status: 'not_started',
    current_step: 'guests',
    completed_at: null,
    window: { opens_on: '2026-09-28', is_open: true, reason: null },
    settings: { require_document_photo: true, require_signature: true },
    terms: { es: 'Confirmo que los datos son verdaderos.', en: 'I confirm the data is true.' },
    travel_reasons: ['leisure', 'business', 'family', 'education', 'health', 'religion', 'shopping', 'transit', 'other'],
    property,
    reservation,
    stays: [stay],
    guests: [bookerSlot, emptyCompanionSlot],
    eta: null,
    signature: { signed: false, accepted_terms_at: null },
    missing: [
      { code: 'guest_data', slot: 0, stay_id: 'stay-1', guest_id: 'guest-booker' },
      { code: 'guest_data', slot: 1, stay_id: 'stay-1', guest_id: null },
      { code: 'document', guest_id: 'guest-booker' },
      { code: 'signature' },
    ],
    balance: { total: '761600.00', paid: '0.00', due: '761600.00', currency: 'COP', can_pay: true },
    ...overrides,
  }
}

/** The check-in once both guests are registered (companion created by the guests step). */
export function registeredCheckin(overrides: Partial<CheckinPayload> = {}): CheckinPayload {
  return makeCheckin({
    status: 'in_progress',
    current_step: 'documents',
    guests: [
      {
        ...bookerSlot,
        complete: true,
        data: { ...bookerSlot.data, birth_date: '1990-04-02' },
        travel: { travel_reason: 'leisure', origin: 'Bogotá', destination: 'Cartagena' },
      },
      {
        ...emptyCompanionSlot,
        guest_id: 'guest-ana',
        complete: true,
        data: { first_name: 'Ana', last_name: 'Pérez', nationality: 'CO', document_type: 'CC', document_hint: '••••4050' },
      },
    ],
    missing: [{ code: 'document', guest_id: 'guest-booker' }, { code: 'document', guest_id: 'guest-ana' }, { code: 'signature' }],
    ...overrides,
  })
}

export function makeStaffCheckin(overrides: Partial<StaffCheckin> = {}): StaffCheckin {
  return {
    reservation_id: 'res-1',
    code: 'HT-7K2M9Q',
    status: 'completed',
    current_step: 'done',
    completed_at: '2026-10-02T09:15:00-05:00',
    accepted_terms_at: '2026-10-02T09:14:00-05:00',
    eta: '16:30',
    ip: '181.52.10.4',
    user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)',
    signature_url: '/api/v1/guestportal/reservations/res-1/checkin/signature/',
    window: { opens_on: '2026-09-28', is_open: true, reason: null },
    guests: [
      {
        slot: 0,
        stay_id: 'stay-1',
        role: 'booker',
        guest_id: 'guest-booker',
        complete: true,
        is_adult: true,
        data: {
          first_name: 'Laura',
          last_name: 'Gómez',
          full_name: 'Laura Gómez',
          document_type: 'CC',
          document_number: '52123456',
          nationality: 'CO',
          country_of_residence: 'CO',
          city_of_residence: 'Bogotá',
          birth_date: '1990-04-02',
          email: 'laura@example.com',
          phone: '+573001234567',
          is_foreign_non_resident: false,
        },
        travel: { travel_reason: 'business', origin: 'Bogotá', destination: 'Cartagena' },
        documents: [
          {
            id: 'doc-1',
            kind: 'id_front',
            uploaded_via: 'portal',
            created_at: '2026-10-02T09:10:00-05:00',
            file_url: '/api/v1/guests/documents/doc-1/file/',
          },
        ],
      },
    ],
    missing: [],
    requests: [],
    portal_url: `http://localhost:5173/g/${TOKEN}`,
    checkin_url: `http://localhost:5173/g/${TOKEN}/checkin`,
    ...overrides,
  }
}
