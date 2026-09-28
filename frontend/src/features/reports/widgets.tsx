import type { DashboardWidget } from '@/app/extensions'
import { OccupancyWidgetSlot } from './components/OccupancyWidgetSlot'

// Today panel extension (plan §E, owner C10): occupancy of the next 14 nights. C1 renders it via `useWidgets()`.
export const widgets: DashboardWidget[] = [
  { id: 'reports-occupancy-14', order: 35, size: 'md', permission: 'reports.operational', Component: OccupancyWidgetSlot },
]
