import { Users } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `guests` feature (plan §E). Owner: B3.
export const nav: NavItem[] = [
  { id: 'guests', section: 'operations', labelKey: 'guests:nav.guests', icon: Users, path: '/app/guests', permission: 'guests.view', order: 40 },
]
