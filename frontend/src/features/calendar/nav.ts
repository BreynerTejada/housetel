import { CalendarDays } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `calendar` feature (plan §E). Owner: C13.
export const nav: NavItem[] = [
  { id: 'calendar', section: 'operations', labelKey: 'calendar:nav.calendar', icon: CalendarDays, path: '/app/calendar', permission: 'bookings.view', order: 20 },
]
