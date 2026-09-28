import type { ReservationDetail, StayDetail } from '../api'

export type StayAction = 'checkin' | 'checkout' | 'assign' | 'modify' | 'cancel'

const ACTIVE = new Set(['tentative', 'confirmed', 'checked_in'])

/** Rooms of the reservation still active (waiting to arrive or in house). */
export function activeStays(reservation: Pick<ReservationDetail, 'stays'>): StayDetail[] {
  return reservation.stays.filter((stay) => ACTIVE.has(stay.status))
}

/**
 * What the desk can do with a stay now (state and business date; permissions are checked by the caller).
 * `activeCount`: active rooms of its reservation — cancelling one room on its own (pilot P3) makes sense when
 * there are others; the last one is cancelled with the whole reservation from the actions menu.
 */
export function stayActions(stay: StayDetail, bd: string, activeCount = 1): StayAction[] {
  const pending = stay.status === 'tentative' || stay.status === 'confirmed'
  const inHouse = stay.status === 'checked_in'
  const actions: StayAction[] = []
  if (pending && stay.checkin_date <= bd) actions.push('checkin')
  if (inHouse) actions.push('checkout')
  if (pending || inHouse) actions.push('assign', 'modify')
  if (pending && activeCount > 1) actions.push('cancel')
  return actions
}
