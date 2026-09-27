import type { DuplicateGuest, Guest, GuestSummary, Page } from '../api'

export function makeGuestSummary(overrides: Partial<GuestSummary> = {}): GuestSummary {
  return {
    id: 'guest-ana',
    first_name: 'Ana María',
    last_name: 'Pérez Gómez',
    full_name: 'Ana María Pérez Gómez',
    email: 'ana.perez@example.com',
    phone: '+573001112233',
    document_type: 'CC',
    document_number: '52123456',
    nationality: 'CO',
    country_of_residence: 'CO',
    city_of_residence: 'Medellín',
    language: 'es',
    is_vip: false,
    blacklisted: false,
    tags: [],
    is_foreign_non_resident: false,
    anonymized_at: null,
    stays_count: 3,
    reservations_count: 4,
    last_stay_date: '2026-06-01',
    created_at: '2024-03-02T10:00:00-05:00',
    ...overrides,
  }
}

export function makeGuest(overrides: Partial<Guest> = {}): Guest {
  return {
    ...makeGuestSummary(),
    birth_date: '1990-05-01',
    gender: 'F',
    address: 'Calle 10 # 43-12',
    notes: '',
    preferences: {},
    marketing_consent: false,
    data_processing_consent_at: '2025-03-12T15:20:00-05:00',
    custom_values: {},
    merged_into: null,
    updated_at: '2026-09-20T10:00:00-05:00',
    documents_count: 0,
    stats: {
      reservations_count: 4,
      stays_count: 3,
      nights: 8,
      total_spent: '2450000.00',
      cancellations: 1,
      no_shows: 0,
      last_stay: {
        reservation_id: 'res-1',
        code: 'HT-7K2M9Q',
        property_id: 'prop-1',
        property_name: 'Hotel Casa Aurora',
        checkin: '2026-06-01',
        checkout: '2026-06-04',
        status: 'checked_out',
      },
      next_stay: null,
    },
    ...overrides,
  }
}

export function makeDuplicate(overrides: Partial<DuplicateGuest> = {}): DuplicateGuest {
  return {
    ...makeGuestSummary({
      id: 'guest-dup',
      first_name: 'Ana',
      last_name: 'Perez',
      full_name: 'Ana Perez',
      email: '',
      document_type: '',
      city_of_residence: '',
      stays_count: 1,
      reservations_count: 1,
    }),
    reasons: ['document'],
    ...overrides,
  }
}

export function page<T>(results: T[]): Page<T> {
  return { count: results.length, next: null, previous: null, results }
}
