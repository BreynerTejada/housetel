import type { StayDetail } from '../api'

export type StayAction = 'checkin' | 'checkout' | 'assign' | 'modify'

/** What the desk can do with a stay now (state and business date; permissions are checked by the caller). */
export function stayActions(stay: StayDetail, bd: string): StayAction[] {
  const pending = stay.status === 'tentative' || stay.status === 'confirmed'
  const inHouse = stay.status === 'checked_in'
  const actions: StayAction[] = []
  if (pending && stay.checkin_date <= bd) actions.push('checkin')
  if (inHouse) actions.push('checkout')
  if (pending || inHouse) actions.push('assign', 'modify')
  return actions
}
