import type { DashboardWidget } from '@/app/extensions'
import { CleaningProgress } from './components/CleaningProgress'

// Today panel (C1, `useWidgets()`): the day's cleaning progress.
export const widgets: DashboardWidget[] = [
  { id: 'housekeeping.progress', order: 40, size: 'md', permission: 'housekeeping.view', Component: CleaningProgress },
]
