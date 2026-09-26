import { ChartColumn } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `reports` feature (plan §E). Owner: C10.
export const nav: NavItem[] = [
  { id: 'reports', section: 'insights', labelKey: 'reports:nav.reports', icon: ChartColumn, path: '/app/reports', permission: 'reports.operational', order: 10 },
]
