import type { ReservationTab } from '@/app/extensions'
import { ReservationHistoryTabLazy } from './components/lazy'

// Owner: C12. The reservation detail (C1) renders it through `useReservationTabs()`: the reservation's audit trail.
export const reservationTabs: ReservationTab[] = [
  { id: 'control-history', labelKey: 'control:history.tab', order: 90, permission: 'control.audit', Component: ReservationHistoryTabLazy },
]
