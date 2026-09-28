import type { ReservationTab } from '@/app/extensions'
import { ReservationMessagesTab } from './components/MessagesTab'

// Owner: C6. The reservation detail (C1) renders these tabs through `useReservationTabs()`.
export const reservationTabs: ReservationTab[] = [
  { id: 'messages', labelKey: 'messaging:tab.label', order: 35, permission: 'messaging.view', Component: ReservationMessagesTab },
]
