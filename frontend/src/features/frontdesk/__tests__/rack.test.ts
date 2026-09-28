import { describe, expect, it } from 'vitest'
import type { RackRoom } from '../api'
import { groupByFloor, keyState } from '../lib/rack'

function room(overrides: Partial<RackRoom> = {}): RackRoom {
  return {
    id: 'room-101',
    number: '101',
    floor: '1',
    room_type: { id: 'rt-dbl', code: 'DBL', color: '#4E6C88', kind: 'private' },
    housekeeping_status: 'clean',
    blocked: false,
    occupant: null,
    arrival: null,
    beds: null,
    ...overrides,
  }
}

const occupant = { stay_id: 'stay-9', reservation_id: 'res-9', guest_name: 'Pedro Díaz', checkout: '2026-10-03', departing: false }
const arrival = { stay_id: 'stay-1', reservation_id: 'res-1', guest_name: 'Valeria Mejía', checkin: '2026-10-01', late: false }

describe('keyState', () => {
  it('a free room shows its housekeeping state and books it', () => {
    expect(keyState(room({ housekeeping_status: 'dirty' }))).toEqual({
      tone: 'dirty',
      arriving: false,
      departing: false,
      action: { kind: 'book' },
    })
  })

  it('a guest staying tonight makes it occupied and opens the reservation', () => {
    expect(keyState(room({ occupant }))).toEqual({
      tone: 'occupied',
      arriving: false,
      departing: false,
      action: { kind: 'open', reservationId: 'res-9' },
    })
  })

  it('a guest leaving today is checked out from the key', () => {
    const state = keyState(room({ occupant: { ...occupant, departing: true }, arrival }))

    expect(state).toEqual({
      tone: 'occupied',
      arriving: true,
      departing: true,
      action: { kind: 'checkout', stayId: 'stay-9', reservationId: 'res-9' },
    })
  })

  it('an arrival keeps the housekeeping tint (is the room ready?) and checks the guest in', () => {
    expect(keyState(room({ arrival, housekeeping_status: 'inspected' }))).toEqual({
      tone: 'inspected',
      arriving: true,
      departing: false,
      action: { kind: 'checkin', stayId: 'stay-1', reservationId: 'res-1' },
    })
  })

  it('blocked and out-of-service rooms cannot be booked from the rack', () => {
    expect(keyState(room({ blocked: true })).action).toEqual({ kind: 'none' })
    expect(keyState(room({ blocked: true })).tone).toBe('blocked')
    expect(keyState(room({ housekeeping_status: 'out_of_service' }))).toMatchObject({ tone: 'blocked', action: { kind: 'none' } })
  })

  it('a dorm is a room of beds: it opens the calendar', () => {
    const dorm = room({
      number: 'D1',
      room_type: { id: 'rt-dorm', code: 'D6', color: '#5F7F66', kind: 'dorm' },
      beds: { total: 6, occupied: 4, departing: 1, arriving: 2, blocked: 0 },
    })

    expect(keyState(dorm)).toEqual({ tone: 'clean', arriving: true, departing: true, action: { kind: 'calendar' } })
  })
})

describe('groupByFloor', () => {
  it('keeps the order of the rack and names each floor once', () => {
    const rooms = [room({ id: 'a', number: '101', floor: '1' }), room({ id: 'b', number: '102', floor: '1' }), room({ id: 'c', number: '201', floor: '2' }), room({ id: 'd', number: 'PH', floor: '' })]

    expect(groupByFloor(rooms).map(({ floor, rooms: keys }) => [floor, keys.map((key) => key.number)])).toEqual([
      ['1', ['101', '102']],
      ['2', ['201']],
      ['', ['PH']],
    ])
  })
})
