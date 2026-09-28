import { Building2, HandCoins } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Owner: P4. Corporate clients and receivables (cartera) of the active property.
export const nav: NavItem[] = [
  { id: 'companies', section: 'operations', labelKey: 'corporate:nav.companies', icon: Building2, path: '/app/companies', permission: 'corporate.view', order: 45 },
  { id: 'receivables', section: 'operations', labelKey: 'corporate:nav.receivables', icon: HandCoins, path: '/app/receivables', permission: 'corporate.view', order: 85 },
]
