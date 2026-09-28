import type { CalBlock, CalendarData, CalStay } from '../api'

/**
 * A small hotel + hostel mix, seen from the week of Monday 2026-10-12 (business date 2026-10-13):
 * DBL (private: 101 clean, 102 dirty), STE (private: 301 inspected) and D6 (dorm D1 with beds A and B).
 */
export const IDS = {
  dbl: 'rt-dbl',
  ste: 'rt-ste',
  dorm: 'rt-d6',
  r101: 'room-101',
  r102: 'room-102',
  r301: 'room-301',
  d1: 'room-d1',
  bedA: 'bed-a',
  bedB: 'bed-b',
} as const

export const RANGE_START = '2026-10-12'
export const BUSINESS_DATE = '2026-10-13'

export function makeStay(overrides: Partial<CalStay> & Pick<CalStay, 'id'>): CalStay {
  return {
    reservation_id: `res-${overrides.id}`,
    code: `HT-${overrides.id.toUpperCase().slice(0, 6)}`,
    status: 'confirmed',
    source: 'front_desk',
    channel_code: '',
    guest_name: 'Huésped',
    room_id: null,
    bed_id: null,
    room_type_id: IDS.dbl,
    checkin: '2026-10-13',
    checkout: '2026-10-15',
    adults: 2,
    children: 0,
    balance_due: false,
    is_vip: false,
    ...overrides,
  }
}

export function makeBlock(overrides: Partial<CalBlock> & Pick<CalBlock, 'id' | 'room_id'>): CalBlock {
  return { bed_id: null, start: '2026-10-16', end: '2026-10-18', kind: 'maintenance', reason: '', ...overrides }
}

export function makeCalendar(): CalendarData {
  return {
    room_types: [
      {
        id: IDS.dbl,
        code: 'DBL',
        name: { es: 'Estándar', en: 'Standard' },
        color: '#4E6C88',
        kind: 'private',
        rooms: [
          { id: IDS.r101, number: '101', floor: '1', housekeeping_status: 'clean', beds: [] },
          { id: IDS.r102, number: '102', floor: '1', housekeeping_status: 'dirty', beds: [] },
        ],
      },
      {
        id: IDS.ste,
        code: 'STE',
        name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' },
        color: '#B4583B',
        kind: 'private',
        rooms: [{ id: IDS.r301, number: '301', floor: '3', housekeeping_status: 'inspected', beds: [] }],
      },
      {
        id: IDS.dorm,
        code: 'D6',
        name: { es: 'Dormitorio 6 camas', en: '6-bed dorm' },
        color: '#B98A2E',
        kind: 'dorm',
        rooms: [
          {
            id: IDS.d1,
            number: 'D1',
            floor: '1',
            housekeeping_status: 'clean',
            beds: [
              { id: IDS.bedA, label: 'A' },
              { id: IDS.bedB, label: 'B' },
            ],
          },
        ],
      },
    ],
    stays: [
      makeStay({
        id: 'laura',
        code: 'HT-LAURA1',
        guest_name: 'Laura Gómez',
        room_id: IDS.r101,
        checkin: '2026-10-13',
        checkout: '2026-10-15',
        source: 'phone',
        balance_due: true,
      }),
      makeStay({
        id: 'mateo',
        code: 'HT-MATEO2',
        guest_name: 'Mateo Ruiz',
        status: 'checked_in',
        room_id: IDS.r102,
        checkin: '2026-10-10',
        checkout: '2026-10-14',
        source: 'ota',
        channel_code: 'booksim',
      }),
      makeStay({
        id: 'ana',
        code: 'HT-ANA003',
        guest_name: 'Ana Pérez',
        status: 'tentative',
        checkin: '2026-10-14',
        checkout: '2026-10-16',
      }),
      makeStay({ id: 'luis', code: 'HT-LUIS04', guest_name: 'Luis Díaz', checkin: '2026-10-15', checkout: '2026-10-17' }),
      makeStay({
        id: 'sofia',
        code: 'HT-SOFIA5',
        guest_name: 'Sofía Mejía',
        room_id: IDS.r301,
        checkin: '2026-10-16',
        checkout: '2026-10-18',
        is_vip: true,
      }),
      makeStay({
        id: 'pedro',
        code: 'HT-PEDRO6',
        guest_name: 'Pedro León',
        status: 'checked_out',
        room_id: IDS.r101,
        checkin: '2026-10-09',
        checkout: '2026-10-12',
      }),
      makeStay({
        id: 'bea',
        code: 'HT-BEA007',
        guest_name: 'Beatriz Soto',
        room_type_id: IDS.dorm,
        room_id: IDS.d1,
        bed_id: IDS.bedA,
        checkin: '2026-10-12',
        checkout: '2026-10-15',
        adults: 1,
      }),
      makeStay({
        id: 'carl',
        code: 'HT-CARL08',
        guest_name: 'Carl Jensen',
        room_type_id: IDS.dorm,
        checkin: '2026-10-13',
        checkout: '2026-10-14',
        adults: 1,
      }),
    ],
    blocks: [
      makeBlock({ id: 'block-102', room_id: IDS.r102, start: '2026-10-16', end: '2026-10-18', reason: 'Pintura' }),
      makeBlock({
        id: 'block-d1',
        room_id: IDS.d1,
        start: '2026-10-16',
        end: '2026-10-17',
        kind: 'out_of_service',
        reason: 'Fumigación',
      }),
      makeBlock({
        id: 'block-bed-b',
        room_id: IDS.d1,
        bed_id: IDS.bedB,
        start: '2026-10-17',
        end: '2026-10-19',
        kind: 'out_of_order',
        reason: 'Colchón',
      }),
    ],
    availability: {
      [IDS.dbl]: {
        '2026-10-11': 0,
        '2026-10-12': 1,
        '2026-10-13': 0,
        '2026-10-14': -1,
        '2026-10-15': 0,
        '2026-10-16': 0,
        '2026-10-17': 1,
        '2026-10-18': 2,
      },
      [IDS.ste]: {
        '2026-10-12': 1,
        '2026-10-13': 1,
        '2026-10-14': 1,
        '2026-10-15': 1,
        '2026-10-16': 0,
        '2026-10-17': 0,
        '2026-10-18': 1,
      },
      [IDS.dorm]: {
        '2026-10-12': 1,
        '2026-10-13': 0,
        '2026-10-14': 1,
        '2026-10-15': 2,
        '2026-10-16': 0,
        '2026-10-17': 1,
        '2026-10-18': 2,
      },
    },
  }
}
