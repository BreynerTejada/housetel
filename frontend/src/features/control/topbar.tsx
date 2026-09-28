import type { TopbarItem } from '@/app/extensions'
import { AlertBell } from './components/AlertBell'

// Owner: C12. The alert bell (open alerts, polled every minute) in the staff topbar.
export const topbarItems: TopbarItem[] = [{ id: 'control-alerts', order: 30, permission: 'control.alerts', Component: AlertBell }]
