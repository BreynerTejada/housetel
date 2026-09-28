import type { ReservationTab } from '@/app/extensions'
import { BillingTabLazy } from './components/lazy'

// Owner: P4. The reservation detail (C1) renders it through `useReservationTabs()`: who pays the stay (guest or
// company) and which charges go to the company's folio. `?tab=corporate-billing` opens it.
export const reservationTabs: ReservationTab[] = [
  { id: 'corporate-billing', labelKey: 'corporate:billing.tab', order: 25, permission: 'corporate.view', Component: BillingTabLazy },
]
