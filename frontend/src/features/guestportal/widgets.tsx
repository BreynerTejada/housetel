import type { DashboardWidget } from '@/app/extensions'
import { OnlineCheckinWidgetLazy } from './components/staff/lazy'

// Owner: C5. The Today panel (C1) renders it through `useWidgets()`.
export const widgets: DashboardWidget[] = [
  { id: 'guestportal-checkins', order: 30, size: 'md', permission: 'guestportal.view', Component: OnlineCheckinWidgetLazy },
]
