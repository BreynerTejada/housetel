import type { DashboardWidget } from '@/app/extensions'
import { RecommendationsWidgetSlot } from './components/RecommendationsWidgetSlot'

// Today panel extension (plan §E, owner C8): C1 renders it through `useWidgets()`.
export const widgets: DashboardWidget[] = [
  { id: 'revenue-recommendations', order: 50, size: 'md', permission: 'revenue.view', Component: RecommendationsWidgetSlot },
]
