import type { ReservationTab } from '@/app/extensions'
import { CheckinTabLazy, RequestsTabLazy } from './components/staff/lazy'

// Owner: C5. The reservation detail (C1) renders these tabs through `useReservationTabs()`.
export const reservationTabs: ReservationTab[] = [
  { id: 'guestportal-checkin', labelKey: 'guestportal:tabs.checkin', order: 30, permission: 'guestportal.view', Component: CheckinTabLazy },
  { id: 'guestportal-requests', labelKey: 'guestportal:tabs.requests', order: 31, permission: 'guestportal.view', Component: RequestsTabLazy },
]
