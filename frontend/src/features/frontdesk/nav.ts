import { ClipboardList, MoonStar, Sun, UsersRound } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `frontdesk` feature (plan §E). Owner: C1; groups: pilot P3.
export const nav: NavItem[] = [
  { id: 'today', section: 'operations', labelKey: 'frontdesk:nav.today', icon: Sun, path: '/app', permission: 'frontdesk.view', order: 10 },
  { id: 'reservations', section: 'operations', labelKey: 'frontdesk:nav.reservations', icon: ClipboardList, path: '/app/reservations', permission: 'bookings.view', order: 30 },
  { id: 'groups', section: 'operations', labelKey: 'frontdesk:nav.groups', icon: UsersRound, path: '/app/groups', permission: 'bookings.view', order: 35 },
  { id: 'nightAudit', section: 'tools', labelKey: 'frontdesk:nav.nightAudit', icon: MoonStar, path: '/app/night-audit', permission: 'frontdesk.night_audit', order: 20 },
]
