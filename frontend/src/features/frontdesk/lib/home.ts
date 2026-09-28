import type { NavItem } from '@/app/extensions'

const TODAY = '/app'

/**
 * Where `/app` should send someone who does not run the front desk (no `frontdesk.view`): housekeepers to
 * their rooms, supervisors to the board, maintenance to the tickets, anyone else to the first page they can
 * open. `null` = stay on Today (front desk) or nowhere better to go.
 */
export function landingFor(can: (code?: string) => boolean, nav: NavItem[]): string | null {
  if (can('frontdesk.view')) return null
  if (can('housekeeping.supervise')) return '/app/housekeeping'
  if (can('housekeeping.work')) return '/app/housekeeping/mine'
  if (can('housekeeping.maintenance')) return '/app/maintenance'
  const first = nav.find((item) => item.path !== TODAY && item.path.startsWith(`${TODAY}/`) && can(item.permission))
  return first?.path ?? null
}
