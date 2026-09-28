import type { ChargeType, Proposal, ProposalRoomType, RoomKind } from '../../api'

/** Rate plans `apply` creates for the proposal (backend `onboarding._plans`). */
export function planCodes(proposal: Proposal): string[] {
  const codes = ['FLEX']
  if ((proposal.policies.non_refundable_discount_percent ?? 0) > 0) codes.push('NR')
  if (proposal.policies.breakfast_price) codes.push('BB')
  return codes
}

export function totalRooms(proposal: Proposal): number {
  return proposal.room_types.reduce((sum, item) => sum + (item.units || 0), 0)
}

export const MAX_UNITS = 200

export function clampInt(value: string | number, low: number, high: number, fallback: number): number {
  const number = typeof value === 'number' ? value : parseInt(value, 10)
  if (!Number.isFinite(number)) return fallback
  return Math.min(high, Math.max(low, Math.round(number)))
}

/** Private room for `guests` people: adults up to the capacity, children fill the rest. */
export function withCapacity(item: ProposalRoomType, guests: number): ProposalRoomType {
  const capacity = clampInt(guests, 1, 20, 2)
  return {
    ...item,
    max_occupancy: capacity,
    max_adults: capacity,
    max_children: Math.max(0, capacity - 1),
    base_occupancy: Math.min(2, capacity),
  }
}

/** A dorm with `count` beds (bunks plus one single when the count is odd): the backend derives the beds
 * per dorm from the beds. */
export function withDormBeds(item: ProposalRoomType, count: number): ProposalRoomType {
  const beds = clampInt(count, 1, 40, 6)
  const bunks = Math.floor(beds / 2)
  return {
    ...item,
    beds: [...(bunks ? [{ type: 'bunk' as const, count: bunks }] : []), ...(beds % 2 ? [{ type: 'single' as const, count: 1 }] : [])],
    beds_per_room: beds,
  }
}

export function withKind(item: ProposalRoomType, kind: RoomKind): ProposalRoomType {
  if (kind === item.kind) return item
  if (kind === 'dorm') {
    return withDormBeds(
      { ...item, kind, base_occupancy: 1, max_adults: 1, max_children: 0, max_occupancy: 1, extra_adult_price: '0', extra_child_price: '0' },
      6,
    )
  }
  return withCapacity({ ...item, kind, beds: [{ type: 'queen', count: 1 }], beds_per_room: null }, 2)
}

export function newRoomType(): ProposalRoomType {
  return {
    code: '',
    name: { es: '', en: '' },
    kind: 'private',
    base_occupancy: 2,
    max_adults: 2,
    max_children: 1,
    max_occupancy: 2,
    beds: [{ type: 'queen', count: 1 }],
    beds_per_room: null,
    size_m2: null,
    amenities: [],
    units: 1,
    room_numbers: [],
    base_price: '250000',
    weekend_adjust_percent: 0,
    extra_adult_price: '0',
    extra_child_price: '0',
  }
}

export function newExtra(): Proposal['extras'][number] {
  return { code: '', name: { es: '', en: '' }, price: '', charge_type: 'per_stay' as ChargeType }
}

/** What blocks "Create everything": i18n keys of the problems (empty = ready). */
export function problems(proposal: Proposal): string[] {
  const found: string[] = []
  if (proposal.room_types.length === 0) found.push('onboarding.noRoomTypes')
  if (proposal.room_types.some((item) => !item.name.es.trim())) found.push('onboarding.nameRequired')
  if (proposal.room_types.some((item) => !(Number(item.base_price) > 0))) found.push('onboarding.priceRequired')
  if (proposal.extras.some((extra) => !extra.name.es.trim() || !(Number(extra.price) > 0))) found.push('onboarding.extraIncomplete')
  return found
}

/** Rows whose numbers no longer match their units (or that changed kind) get new numbers from the backend. */
export function needsNumbers(item: ProposalRoomType): boolean {
  if (item.room_numbers.length !== item.units) return true
  const dormNumbers = item.room_numbers.every((number) => /^D\d+$/.test(number))
  return item.kind === 'dorm' ? !dormNumbers : dormNumbers && item.room_numbers.length > 0
}
