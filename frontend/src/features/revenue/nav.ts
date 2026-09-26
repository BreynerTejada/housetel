import { TrendingUp } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `revenue` feature (plan §E). Owner: C8.
export const nav: NavItem[] = [
  { id: 'revenue', section: 'revenue', labelKey: 'revenue:nav.revenue', icon: TrendingUp, path: '/app/revenue', permission: 'revenue.view', order: 40 },
]
