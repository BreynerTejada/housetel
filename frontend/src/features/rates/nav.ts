import { Coffee, Layers, Percent, ShieldCheck, Tags, TicketPercent } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `rates` feature (plan §E). Owner: B2a.
export const nav: NavItem[] = [
  { id: 'rates', section: 'revenue', labelKey: 'rates:nav.rates', icon: Tags, path: '/app/rates', permission: 'rates.view', order: 10 },
  { id: 'ratePlans', section: 'revenue', labelKey: 'rates:nav.ratePlans', icon: Layers, path: '/app/rates/plans', permission: 'rates.view', order: 20 },
  { id: 'promos', section: 'revenue', labelKey: 'rates:nav.promos', icon: TicketPercent, path: '/app/rates/promos', permission: 'rates.view', order: 30 },
  { id: 'taxes', section: 'settings', labelKey: 'rates:nav.taxes', icon: Percent, path: '/app/settings/taxes', permission: 'rates.manage', order: 50, descriptionKey: 'rates:nav.taxesHint' },
  { id: 'policies', section: 'settings', labelKey: 'rates:nav.policies', icon: ShieldCheck, path: '/app/settings/policies', permission: 'rates.manage', order: 60, descriptionKey: 'rates:nav.policiesHint' },
  { id: 'extras', section: 'settings', labelKey: 'rates:nav.extras', icon: Coffee, path: '/app/settings/extras', permission: 'rates.manage', order: 70, descriptionKey: 'rates:nav.extrasHint' },
]
