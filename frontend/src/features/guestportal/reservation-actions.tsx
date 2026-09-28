import { QrCode, Send } from 'lucide-react'
import type { ReservationAction } from '@/app/extensions'
import { LinkQrActionLazy, SendLinkActionLazy } from './components/staff/lazy'

// Owner: C5. The reservation detail (C1) lists these in its actions menu (`useReservationActions()`) and wraps
// each Component in its own dialog: the Component renders only the body and calls `close()` when done.
export const reservationActions: ReservationAction[] = [
  { id: 'guestportal-send-link', labelKey: 'guestportal:actions.sendLink', icon: Send, order: 40, permission: 'guestportal.manage', Component: SendLinkActionLazy },
  { id: 'guestportal-link', labelKey: 'guestportal:actions.copyLink', icon: QrCode, order: 41, permission: 'guestportal.view', Component: LinkQrActionLazy },
]
