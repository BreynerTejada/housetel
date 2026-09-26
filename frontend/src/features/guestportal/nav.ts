import { QrCode } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `guestportal` feature (plan §E). Owner: C5.
export const nav: NavItem[] = [
  { id: 'guestPortal', section: 'settings', labelKey: 'guestportal:nav.guestPortal', icon: QrCode, path: '/app/settings/guest-portal', permission: 'guestportal.manage', order: 90, descriptionKey: 'guestportal:nav.guestPortalHint' },
]
