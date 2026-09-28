import type { NavItem } from '@/app/extensions'

const TODAY = '/app'
const REPORTS = ['reports.operational', 'reports.financial', 'reports.performance']

/**
 * Where `/app` should send someone who does not run the front desk (no `frontdesk.view`), pilot P3: housekeeping
 * supervisors to the board, housekeepers to their rooms, maintenance to the tickets, whoever reads reports
 * (accounting) to Reports, anyone else to the first page of their menu. `null` = stay on Today (front desk) or
 * nowhere better to go.
 */
export function landingFor(can: (code?: string) => boolean, nav: NavItem[]): string | null {
  if (can('frontdesk.view')) return null
  if (can('housekeeping.supervise')) return '/app/housekeeping'
  if (can('housekeeping.work')) return '/app/housekeeping/mine'
  if (can('housekeeping.maintenance')) return '/app/maintenance'
  if (REPORTS.some((code) => can(code)) && nav.some((item) => item.path === '/app/reports')) return '/app/reports'
  const first = nav.find((item) => item.path !== TODAY && item.path.startsWith(`${TODAY}/`) && can(item.permission))
  return first?.path ?? null
}
