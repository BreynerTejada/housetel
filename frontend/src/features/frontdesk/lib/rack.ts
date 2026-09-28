import type { RackRoom } from '../api'

/**
 * The key rack of the Today panel: what each key means for the desk tonight and what clicking it does.
 * Tone = the tint of the key (room-state tokens); markers = a guest arriving or leaving today.
 */
export type KeyTone = 'clean' | 'dirty' | 'inspected' | 'occupied' | 'blocked'

export type KeyAction =
  | { kind: 'checkin'; stayId: string; reservationId: string }
  | { kind: 'checkout'; stayId: string; reservationId: string }
  | { kind: 'open'; reservationId: string }
  | { kind: 'book' }
  | { kind: 'calendar' }
  | { kind: 'none' }

export interface KeyState {
  tone: KeyTone
  arriving: boolean
  departing: boolean
  action: KeyAction
}

function housekeepingTone(room: RackRoom): KeyTone {
  return room.housekeeping_status === 'out_of_service' ? 'blocked' : room.housekeeping_status
}

export function keyState(room: RackRoom): KeyState {
  if (room.blocked || room.housekeeping_status === 'out_of_service') {
    return { tone: 'blocked', arriving: false, departing: false, action: { kind: 'none' } }
  }
  if (room.room_type.kind === 'dorm') {
    const beds = room.beds
    return {
      tone: housekeepingTone(room),
      arriving: Boolean(beds?.arriving),
      departing: Boolean(beds?.departing),
      action: { kind: 'calendar' },
    }
  }
  const { occupant, arrival } = room
  if (occupant) {
    return {
      tone: 'occupied',
      arriving: arrival !== null,
      departing: occupant.departing,
      action: occupant.departing
        ? { kind: 'checkout', stayId: occupant.stay_id, reservationId: occupant.reservation_id }
        : { kind: 'open', reservationId: occupant.reservation_id },
    }
  }
  if (arrival) {
    return {
      tone: housekeepingTone(room),
      arriving: true,
      departing: false,
      action: { kind: 'checkin', stayId: arrival.stay_id, reservationId: arrival.reservation_id },
    }
  }
  return { tone: housekeepingTone(room), arriving: false, departing: false, action: { kind: 'book' } }
}

/** Consecutive rooms of the same floor (the backend already sorts the rack by floor and room order). */
export function groupByFloor(rooms: RackRoom[]): { floor: string; rooms: RackRoom[] }[] {
  const floors: { floor: string; rooms: RackRoom[] }[] = []
  for (const room of rooms) {
    const last = floors.at(-1)
    if (last && last.floor === room.floor) last.rooms.push(room)
    else floors.push({ floor: room.floor, rooms: [room] })
  }
  return floors
}
