import { Landmark, Scale } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `compliance` feature (plan §E). Owner: C7.
export const nav: NavItem[] = [
  { id: 'compliance', section: 'compliance', labelKey: 'compliance:nav.compliance', icon: Landmark, path: '/app/compliance', permission: 'compliance.view', order: 10 },
  { id: 'settingsCompliance', section: 'settings', labelKey: 'compliance:nav.settingsCompliance', icon: Scale, path: '/app/settings/compliance', permission: 'compliance.settings', order: 120, descriptionKey: 'compliance:nav.settingsComplianceHint' },
]
