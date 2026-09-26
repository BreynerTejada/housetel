import { MonitorSmartphone } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `marketplace` feature (plan §E). Owner: C4.
export const nav: NavItem[] = [
  { id: 'bookingEngine', section: 'settings', labelKey: 'marketplace:nav.bookingEngine', icon: MonitorSmartphone, path: '/app/settings/booking-engine', permission: 'marketplace.manage', order: 80, descriptionKey: 'marketplace:nav.bookingEngineHint' },
]
