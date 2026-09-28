import type { HousekeepingStatus, RoomOption, TodayRow } from '../api'

/**
 * The rooms (or dorm beds) a stay can use, as the check-in and "assign room" dialogs list them: the unit it
 * already has, then the free ones of `GET /bookings/stays/{id}/room-options/`. A unit is ready when it is
 * clean or inspected **and** nobody is still in house in it (a guest leaving today who has not checked out:
 * the bookings check-in only looks at the housekeeping status).
 */
export interface UnitOption {
  key: string
  roomId: string
  roomNumber: string
  bedId: string | null
  bedLabel: string | null
  roomTypeCode: string
  housekeepingStatus: HousekeepingStatus
  ready: boolean
  sameCategory: boolean
  /** The unit the stay already has. */
  current: boolean
  /** Name of the guest still in house in this unit (null = vacant, or unknown). */
  occupiedBy: string | null
}

const READY = new Set<HousekeepingStatus>(['clean', 'inspected'])

/** Clean or inspected: the bookings check-in accepts the room without `force`. */
export const isHousekeepingReady = (status: HousekeepingStatus) => READY.has(status)

export const unitKey = (roomId: string, bedId: string | null) => `${roomId}:${bedId ?? ''}`

/** Guests in house by unit key (from the Today board), leaving out the stay being checked in. */
export function occupiedUnits(inHouse: TodayRow[] | undefined, exceptStayId?: string): Map<string, string> {
  const units = new Map<string, string>()
  for (const row of inHouse ?? []) {
    if (!row.room_id || row.stay_id === exceptStayId) continue
    units.set(unitKey(row.room_id, row.bed_id), row.guest_name)
  }
  return units
}

export function currentUnit(
  room: { id: string; number: string; housekeeping_status: HousekeepingStatus } | null,
  bed: { id: string; label: string } | null,
  roomTypeCode: string,
): UnitOption | null {
  if (!room) return null
  return {
    key: unitKey(room.id, bed?.id ?? null),
    roomId: room.id,
    roomNumber: room.number,
    bedId: bed?.id ?? null,
    bedLabel: bed?.label ?? null,
    roomTypeCode,
    housekeepingStatus: room.housekeeping_status,
    ready: READY.has(room.housekeeping_status),
    sameCategory: true,
    current: true,
    occupiedBy: null,
  }
}

function rank(unit: UnitOption): number {
  return (unit.sameCategory ? 0 : 2) + (unit.ready ? 0 : 1)
}

/**
 * The current unit first, then the ready rooms of its category, the rest of its category, other categories.
 * `occupied` (unit key → guest in house) marks units that still have someone inside as not ready.
 */
export function orderUnits(
  current: UnitOption | null,
  options: RoomOption[],
  occupied: Map<string, string> = new Map(),
): UnitOption[] {
  const withOccupant = (unit: UnitOption): UnitOption => {
    const occupiedBy = occupied.get(unit.key) ?? null
    return occupiedBy ? { ...unit, occupiedBy, ready: false } : unit
  }
  const others = options
    .map<UnitOption>((option) => ({
      key: unitKey(option.room_id, option.bed_id),
      roomId: option.room_id,
      roomNumber: option.room_number,
      bedId: option.bed_id,
      bedLabel: option.bed_label,
      roomTypeCode: option.room_type_code,
      housekeepingStatus: option.housekeeping_status,
      ready: option.ready,
      sameCategory: option.same_category,
      current: false,
      occupiedBy: null,
    }))
    .filter((unit) => unit.key !== current?.key)
    .map(withOccupant)
    .map((unit, index) => ({ unit, index }))
    .sort((a, b) => rank(a.unit) - rank(b.unit) || a.index - b.index)
    .map(({ unit }) => unit)
  return current ? [withOccupant(current), ...others] : others
}

/** The unit to propose: the current one when it is ready, else the first ready one of its category. */
export function proposedUnit(units: UnitOption[]): UnitOption | undefined {
  const current = units.find((unit) => unit.current)
  if (current?.ready) return current
  return units.find((unit) => !unit.current && unit.sameCategory && unit.ready) ?? current ?? units.find((unit) => unit.sameCategory)
}
