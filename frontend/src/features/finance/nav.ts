import { Wallet } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `finance` feature (plan §E). Owner: B4.
export const nav: NavItem[] = [
  { id: 'cashier', section: 'operations', labelKey: 'finance:nav.cashier', icon: Wallet, path: '/app/cashier', permission: 'finance.view', order: 80 },
]
