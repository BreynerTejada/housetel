import type { TFunction } from 'i18next'
import { formatDate, formatDateRange, formatMoney, formatNumber, type Lang } from '@/lib/format'
import type { CalBlock, CalendarData, CalStay, I18nText } from '../api'
import { diffDays } from './dates'
import type { MoveTarget, PlanResult } from './dnd'

const NBSP = ' '

/**
 * A nightly price short enough for a day column: "320 mil" / "1,3 M" in Spanish, "320K" / "1.3M" in
 * English. Written by hand instead of `Intl` compact notation, whose wording changes between ICU versions
 * (Node 24 and 26 disagree on "mil" vs "k").
 */
export function compactPrice(value: string | null, lang: Lang): string {
  if (value === null || value === '') return ''
  const amount = Number(value)
  if (!Number.isFinite(amount)) return ''
  if (Math.abs(amount) >= 1_000_000) {
    const millions = formatNumber(amount / 1_000_000, lang, 1)
    return lang === 'es' ? `${millions}${NBSP}M` : `${millions}M`
  }
  if (Math.abs(amount) >= 1_000) {
    const thousands = formatNumber(amount / 1_000, lang, Math.abs(amount) < 100_000 ? 1 : 0)
    return lang === 'es' ? `${thousands}${NBSP}mil` : `${thousands}K`
  }
  return formatNumber(amount, lang, 0)
}

/** Channel names people know (OTA codes of the simulators and common ones). */
const CHANNEL_NAMES: Record<string, string> = {
  booksim: 'BookSim',
  airsim: 'AirSim',
  booking: 'Booking.com',
  expedia: 'Expedia',
  airbnb: 'Airbnb',
}

export function pick(text: I18nText | string | undefined, lang: Lang): string {
  if (!text) return ''
  if (typeof text === 'string') return text
  return text[lang] || text.es || text.en || ''
}

/** Where a booking came from: the OTA's name when there is one, otherwise the source. */
export function sourceLabel(t: TFunction, stay: Pick<CalStay, 'source' | 'channel_code'>): string {
  if (stay.channel_code) return CHANNEL_NAMES[stay.channel_code.toLowerCase()] ?? stay.channel_code
  const key = `calendar:sources.${stay.source}`
  return t(key, { defaultValue: stay.source })
}

export interface RoomIndex {
  rooms: Map<string, { number: string; roomTypeId: string; status: string; isDorm: boolean }>
  beds: Map<string, { label: string; roomNumber: string }>
  roomTypeNames: Map<string, I18nText>
}

export function indexRooms(data: CalendarData): RoomIndex {
  const index: RoomIndex = { rooms: new Map(), beds: new Map(), roomTypeNames: new Map() }
  for (const roomType of data.room_types) {
    index.roomTypeNames.set(roomType.id, roomType.name)
    for (const room of roomType.rooms) {
      index.rooms.set(room.id, {
        number: room.number,
        roomTypeId: roomType.id,
        status: room.housekeeping_status,
        isDorm: roomType.kind === 'dorm' || room.beds.length > 0,
      })
      for (const bed of room.beds) index.beds.set(bed.id, { label: bed.label, roomNumber: room.number })
    }
  }
  return index
}

/** Short place of a stay for bars and toasts: "Hab. 101", "Cama A · D1" or "Sin asignar". */
export function placeLabel(t: TFunction, index: RoomIndex, roomId: string | null, bedId: string | null): string {
  if (bedId) {
    const bed = index.beds.get(bedId)
    if (bed) return t('calendar:bar.bed', { label: bed.label, room: bed.roomNumber })
  }
  if (roomId) {
    const room = index.rooms.get(roomId)
    if (room) return t('calendar:bar.room', { number: room.number })
  }
  return t('calendar:bar.unassigned')
}

export function nightsOf(stay: Pick<CalStay, 'checkin' | 'checkout'>): number {
  return Math.max(0, diffDays(stay.checkin, stay.checkout))
}

/**
 * Accessible name of a bar, in reading order: guest · code · status · dates · nights · place · VIP ·
 * balance due · upgrade · channel.
 */
export function stayLabel(t: TFunction, lang: Lang, stay: CalStay, index: RoomIndex): string {
  const parts = [
    stay.guest_name,
    stay.code,
    t(`status.reservation.${stay.status}`, { ns: 'common' }),
    formatDateRange(stay.checkin, stay.checkout, lang),
    t('date.nights', { ns: 'common', count: nightsOf(stay) }),
    placeLabel(t, index, stay.room_id, stay.bed_id),
  ]
  if (stay.is_vip) parts.push(t('calendar:bar.vip'))
  if (stay.balance_due) parts.push(t('calendar:bar.balanceDue'))
  const roomType = stay.room_id ? index.rooms.get(stay.room_id)?.roomTypeId : undefined
  if (roomType && roomType !== stay.room_type_id) {
    parts.push(t('calendar:bar.upgrade', { category: pick(index.roomTypeNames.get(stay.room_type_id), lang) }))
  }
  parts.push(sourceLabel(t, stay))
  return parts.join(' · ')
}

export function blockKindLabel(t: TFunction, kind: string): string {
  return t(`calendar:block.kinds.${kind}`, { defaultValue: kind })
}

/** "Bloqueada · Mantenimiento · Pintura · 16–18 oct 2026" (the end day is free again). */
export function blockLabel(t: TFunction, lang: Lang, block: CalBlock): string {
  return [t('calendar:block.blocked'), blockKindLabel(t, block.kind), block.reason, formatDateRange(block.start, block.end, lang)]
    .filter(Boolean)
    .join(' · ')
}

/** Accent-insensitive search on guest name and booking code. */
export function normalizeSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

export function matchesSearch(stay: Pick<CalStay, 'guest_name' | 'code'>, query: string): boolean {
  const needle = normalizeSearch(query)
  if (!needle) return false
  return normalizeSearch(stay.guest_name).includes(needle) || normalizeSearch(stay.code).includes(needle)
}

/** Where a moved (or new) stay would go, in words: "Cama B · D1", "Dormitorio D1", "Hab. 101", "Sin asignar · Suite". */
export function targetLabel(t: TFunction, lang: Lang, index: RoomIndex, target: Pick<MoveTarget, 'roomTypeId' | 'roomId' | 'bedId'>): string {
  const room = target.roomId ? index.rooms.get(target.roomId) : undefined
  if (target.bedId || !room) {
    if (target.bedId || target.roomId) return placeLabel(t, index, target.roomId, target.bedId)
    return t('calendar:grid.rowUnassigned', { name: pick(index.roomTypeNames.get(target.roomTypeId), lang) })
  }
  return room.isDorm ? t('calendar:grid.rowDorm', { number: room.number }) : t('calendar:bar.room', { number: room.number })
}

/**
 * Why a stay cannot go where it was dropped, naming whoever is in the way, why the room is blocked or which
 * category is full on which night.
 */
export function invalidText(t: TFunction, result: Extract<PlanResult, { kind: 'invalid' }>, lang: Lang = 'es'): string {
  const { conflict } = result
  if (conflict?.type === 'stay') return t(`calendar:invalid.${result.reason}`, { guest: conflict.guest, code: conflict.code })
  if (conflict?.type === 'block') return t(`calendar:invalid.${result.reason}`, { reason: conflict.reason || blockKindLabel(t, conflict.kind) })
  if (conflict?.type === 'units') {
    return t(`calendar:invalid.${result.reason}`, { category: pick(conflict.category, lang), date: formatDate(conflict.date, 'EEE d MMM', lang) })
  }
  return t(`calendar:invalid.${result.reason}`)
}

/** Where a new booking would go, as the end of "Nueva reserva en …": "la 101", "la cama A de D1", "Suite sin habitación". */
export function newPlaceLabel(t: TFunction, lang: Lang, index: RoomIndex, target: Pick<MoveTarget, 'roomTypeId' | 'roomId' | 'bedId'>): string {
  if (target.bedId) {
    const bed = index.beds.get(target.bedId)
    if (bed) return t('calendar:grid.placeBed', { label: bed.label, room: bed.roomNumber })
  }
  const room = target.roomId ? index.rooms.get(target.roomId) : undefined
  if (room) return room.isDorm ? t('calendar:grid.placeDorm', { number: room.number }) : t('calendar:grid.placeRoom', { number: room.number })
  return t('calendar:grid.placeUnassigned', { category: pick(index.roomTypeNames.get(target.roomTypeId), lang) })
}

/** A difference of money with its sign: "+$ 56.800", "−$ 12.000", "$ 0". */
export function signedMoney(value: string | number, currency = 'COP'): string {
  const amount = Number(value)
  if (!Number.isFinite(amount) || amount === 0) return formatMoney(0, currency)
  return `${amount > 0 ? '+' : '−'}${formatMoney(Math.abs(amount), currency)}`
}
