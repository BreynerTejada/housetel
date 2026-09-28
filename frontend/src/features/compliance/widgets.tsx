import type { DashboardWidget } from '@/app/extensions'
import { LegalWidgetLazy } from './components/lazy'

// Owner: C7. Today panel (C1, `useWidgets()`): legal work still pending (invoices, TRA, SIRE).
export const widgets: DashboardWidget[] = [
  { id: 'compliance.pending', order: 60, size: 'md', permission: 'compliance.view', Component: LegalWidgetLazy },
]
