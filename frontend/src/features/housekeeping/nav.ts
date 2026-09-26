import { BrushCleaning, Wrench } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `housekeeping` feature (plan §E). Owner: C2.
export const nav: NavItem[] = [
  { id: 'housekeeping', section: 'operations', labelKey: 'housekeeping:nav.housekeeping', icon: BrushCleaning, path: '/app/housekeeping', permission: 'housekeeping.view', order: 60 },
  { id: 'maintenance', section: 'operations', labelKey: 'housekeeping:nav.maintenance', icon: Wrench, path: '/app/maintenance', permission: 'housekeeping.view', order: 70 },
  { id: 'settingsHousekeeping', section: 'settings', labelKey: 'housekeeping:nav.settingsHousekeeping', icon: BrushCleaning, path: '/app/settings/housekeeping', permission: 'housekeeping.supervise', order: 110, descriptionKey: 'housekeeping:nav.settingsHousekeepingHint' },
]
