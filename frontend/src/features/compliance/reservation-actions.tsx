import { ReceiptText } from 'lucide-react'
import type { ReservationAction } from '@/app/extensions'
import { IssueInvoiceActionLazy } from './components/lazy'

// Owner: C7. Listed in the reservation's actions menu (C1, `useReservationActions()`); C1 wraps the component in a
// dialog titled with `labelKey` and passes `close()`.
export const reservationActions: ReservationAction[] = [
  {
    id: 'compliance-issue-invoice',
    labelKey: 'compliance:issue.action',
    icon: ReceiptText,
    order: 60,
    permission: 'compliance.invoice',
    Component: IssueInvoiceActionLazy,
  },
]
