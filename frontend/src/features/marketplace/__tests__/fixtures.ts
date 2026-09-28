import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import type { Destination, EngineConfig, Offer, OffersResponse, PropertyCard, PropertyDetail, SearchResponse } from '../api'

export const PUBLIC = '/api/v1/public/marketplace'

export const DBL = '6ffbff0e-c5bf-4b8d-add8-bc49472b746d'
export const STE = '1670a4e3-0000-4000-8000-000000000003'
export const FLEX = 'fafa56fb-9421-42e7-a0a3-d453fc97ac2b'
export const NR = 'aa11aa11-0000-4000-8000-000000000002'
export const BRK = 'b0b0b0b0-0000-4000-8000-000000000009'

export const destinations: Destination[] = [
  { city: 'Bogotá', department: 'Cundinamarca', properties_count: 1, cover_photo: '/media/photos/seed/andino-hostel-bogota-1.jpg' },
  { city: 'Cartagena', department: 'Bolívar', properties_count: 2, cover_photo: '/media/photos/seed/casa-aurora-1.jpg' },
  { city: 'Medellín', department: 'Antioquia', properties_count: 1, cover_photo: null },
]

export function makeCard(overrides: Partial<PropertyCard> = {}): PropertyCard {
  return {
    slug: 'casa-aurora',
    name: 'Hotel Casa Aurora',
    property_type: 'boutique',
    star_rating: 4,
    city: 'Cartagena',
    department: 'Bolívar',
    neighborhood: 'Centro Histórico',
    tagline: { es: 'Casa colonial restaurada con piscina en la terraza.', en: 'Restored colonial house with a rooftop pool.' },
    highlights: [],
    photo: '/media/photos/seed/casa-aurora-1.jpg',
    photos: [],
    amenities: [
      { code: 'pool', name: { es: 'Piscina', en: 'Pool' }, icon: 'waves-ladder', category: 'property' },
      { code: 'wifi', name: { es: 'Wifi', en: 'Wi-Fi' }, icon: 'wifi', category: 'room' },
    ],
    currency: 'COP',
    offer: null,
    ...overrides,
  }
}

export function makeSearch(overrides: Partial<SearchResponse> = {}): SearchResponse {
  const results = overrides.results ?? [makeCard()]
  return {
    count: results.length,
    city: '',
    checkin: null,
    checkout: null,
    nights: 0,
    adults: 2,
    children: 0,
    results,
    facets: { types: [], stars: [], amenities: [] },
    ...overrides,
  }
}

const flexPolicy = {
  id: 'p-flex',
  name: { es: 'Flexible 48h', en: 'Flexible 48h' },
  description: {},
  non_refundable: false,
  free_until_hours_before: 48,
  penalty_type: 'first_night' as const,
  penalty_value: '0.00',
}

const strictPolicy = { ...flexPolicy, id: 'p-nr', name: { es: 'No reembolsable', en: 'Non-refundable' }, non_refundable: true }

export function makeDetail(overrides: Partial<PropertyDetail> = {}): PropertyDetail {
  const card = makeCard()
  return {
    slug: card.slug,
    name: card.name,
    property_type: card.property_type,
    star_rating: card.star_rating,
    city: card.city,
    department: card.department,
    neighborhood: card.neighborhood,
    tagline: card.tagline,
    highlights: [{ es: 'Piscina y bar en la terraza', en: 'Rooftop pool and bar' }],
    photo: card.photo,
    currency: 'COP',
    description: { es: 'Casa colonial del siglo XVII en el Centro Histórico.', en: 'A 17th-century colonial house in the old town.' },
    address: 'Calle del Cuartel #36-77',
    country: 'CO',
    latitude: '10.423600',
    longitude: '-75.551800',
    phone: '+57 605 660 1234',
    email: 'reservas@casaaurora.co',
    website: 'https://casaaurora.co',
    rnt_number: 'RNT 98765',
    check_in_time: '15:00',
    check_out_time: '12:00',
    house_rules: { es: 'Silencio desde las 22:00.', en: 'Quiet hours from 10 pm.' },
    policies: { pets_allowed: false, smoking_allowed: false, children_allowed: true, events_allowed: false, min_checkin_age: 18 },
    languages: ['es', 'en'],
    amenities: card.amenities,
    photos: [
      { id: 'ph-1', url: '/media/photos/seed/casa-aurora-1.jpg', caption: {} },
      { id: 'ph-2', url: '/media/photos/seed/casa-aurora-2.jpg', caption: {} },
    ],
    hero_image: '/media/photos/seed/casa-aurora-1.jpg',
    room_types: [
      {
        id: DBL,
        code: 'DBL',
        name: { es: 'Estándar', en: 'Standard' },
        description: { es: 'Habitación con cama queen.', en: 'Room with a queen bed.' },
        kind: 'private',
        base_occupancy: 2,
        max_adults: 2,
        max_children: 1,
        max_occupancy: 3,
        beds: [{ type: 'queen', count: 1 }],
        size_m2: '22.00',
        size_m2_range: null,
        views: ['city'],
        smoking_allowed: false,
        accessible: false,
        amenities: [],
        photos: [],
        features: [],
        units_count: 10,
      },
      {
        id: STE,
        code: 'STE',
        name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' },
        description: {},
        kind: 'private',
        base_occupancy: 2,
        max_adults: 3,
        max_children: 2,
        max_occupancy: 4,
        beds: [{ type: 'king', count: 1 }],
        size_m2: '42.00',
        size_m2_range: null,
        views: ['sea'],
        smoking_allowed: false,
        accessible: false,
        amenities: [],
        photos: [],
        features: [],
        units_count: 6,
      },
    ],
    cancellation_policies: [flexPolicy, strictPolicy],
    extras: [
      { id: BRK, code: 'BRK', name: { es: 'Desayuno', en: 'Breakfast' }, price: '35000.00', charge_type: 'per_person_night', tax_rate: '19.00', tax_included: false },
    ],
    headline: { es: 'Una casa colonial para despertar dentro de la muralla', en: 'A colonial house inside the walls' },
    terms: { es: 'No se admiten mascotas.', en: 'No pets.' },
    booking: {
      earliest_checkin: '2026-10-01',
      latest_checkin: '2027-10-01',
      max_nights: 30,
      min_advance_hours: 0,
      max_advance_days: 365,
      show_promo_field: true,
      online_payments: true,
    },
    brand: { primary_color: '#0E6E74', logo: '' },
    marketplace_listed: true,
    booking_engine_enabled: true,
    via: 'marketplace',
    ...overrides,
  }
}

export function makeOffer(roomTypeId: string, ratePlanId: string, total: string, overrides: Partial<Offer> = {}): Offer {
  const suite = roomTypeId === STE
  const flex = ratePlanId === FLEX
  return {
    room_type_id: roomTypeId,
    rate_plan_id: ratePlanId,
    room_type: {
      id: roomTypeId,
      code: suite ? 'STE' : 'DBL',
      name: suite ? { es: 'Suite Vista al Mar', en: 'Sea View Suite' } : { es: 'Estándar', en: 'Standard' },
      kind: 'private',
      max_adults: suite ? 3 : 2,
      max_children: suite ? 2 : 1,
      max_occupancy: suite ? 4 : 3,
      photo: null,
    },
    rate_plan: {
      id: ratePlanId,
      code: flex ? 'FLEX' : 'NR',
      name: flex ? { es: 'Tarifa flexible', en: 'Flexible rate' } : { es: 'No reembolsable', en: 'Non-refundable' },
      meal_plan: 'room_only',
      deposit_percent: '0.00',
      requires_payment: false,
      cancellation_policy: flex ? flexPolicy : strictPolicy,
    },
    available_units: 2,
    units_needed: 1,
    max_quantity: 2,
    quote: { nights: [], discount_total: '0.00', promo_applied: null },
    net_total: total,
    tax_total: '0.00',
    total,
    per_night: String(Number(total) / 2),
    tax_exempt: false,
    promo_applied: null,
    ...overrides,
  }
}

export function makeOffers(offers: Offer[], overrides: Partial<OffersResponse> = {}): OffersResponse {
  return {
    checkin: '2026-10-09',
    checkout: '2026-10-11',
    nights: 2,
    adults: 2,
    children: 0,
    currency: 'COP',
    tax_exempt: false,
    online_payments: true,
    promo: null,
    offers,
    ...overrides,
  }
}

export function makeEngineConfig(overrides: Partial<EngineConfig> = {}): EngineConfig {
  return {
    slug: 'casa-aurora',
    name: 'Hotel Casa Aurora',
    city: 'Cartagena',
    department: 'Bolívar',
    property_type: 'boutique',
    star_rating: 4,
    address: 'Calle del Cuartel #36-77',
    phone: '+57 605 660 1234',
    email: 'reservas@casaaurora.co',
    currency: 'COP',
    enabled: true,
    primary_color: '#0E6E74',
    logo: '',
    hero_image: null,
    headline: { es: 'Una casa colonial para despertar dentro de la muralla' },
    show_promo_field: true,
    terms: {},
    booking: { earliest_checkin: '2026-10-01', latest_checkin: '2027-10-01', max_nights: 30, online_payments: true },
    languages: ['es', 'en'],
    ...overrides,
  }
}

/** Serves the public catalog endpoints the home page reads. */
export function serveHome(search: SearchResponse = makeSearch()) {
  server.use(
    http.get(`${PUBLIC}/destinations/`, () => HttpResponse.json(destinations)),
    http.get(`${PUBLIC}/search/`, () => HttpResponse.json(search)),
  )
}
