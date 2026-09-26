import { Building, CreditCard, Gauge, HandCoins, Package, Receipt, Rocket } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `saas` feature (plan §E). Owner: C11.
export const nav: NavItem[] = [
  { id: 'gettingStarted', section: 'tools', labelKey: 'saas:nav.gettingStarted', icon: Rocket, path: '/app/getting-started', order: 5 },
  { id: 'billing', section: 'settings', labelKey: 'saas:nav.billing', icon: CreditCard, path: '/app/settings/billing', permission: 'saas.billing_view', order: 200, descriptionKey: 'saas:nav.billingHint' },
  { id: 'adminHome', section: 'admin', labelKey: 'saas:nav.adminHome', icon: Gauge, path: '/admin', order: 10, platformAdmin: true },
  { id: 'adminOrgs', section: 'admin', labelKey: 'saas:nav.adminOrgs', icon: Building, path: '/admin/organizations', order: 20, platformAdmin: true },
  { id: 'adminPlans', section: 'admin', labelKey: 'saas:nav.adminPlans', icon: Package, path: '/admin/plans', order: 30, platformAdmin: true },
  { id: 'adminBilling', section: 'admin', labelKey: 'saas:nav.adminBilling', icon: Receipt, path: '/admin/billing', order: 40, platformAdmin: true },
  { id: 'adminCommissions', section: 'admin', labelKey: 'saas:nav.adminCommissions', icon: HandCoins, path: '/admin/commissions', order: 50, platformAdmin: true },
]
