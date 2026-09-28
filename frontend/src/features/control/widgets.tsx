import type { DashboardWidget } from '@/app/extensions'
import { AlertsWidgetLazy } from './components/lazy'

// Owner: C12. Today panel (C1, `useWidgets()`): the hotel's open alerts, most severe first.
export const widgets: DashboardWidget[] = [
  { id: 'control.alerts', order: 20, size: 'md', permission: 'control.alerts', Component: AlertsWidgetLazy },
]
