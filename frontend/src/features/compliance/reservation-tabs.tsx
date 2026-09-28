import type { ReservationTab } from '@/app/extensions'
import { LegalTabLazy } from './components/lazy'

// Owner: C7. The reservation detail (C1) renders it through `useReservationTabs()`: invoice(s), TRA and SIRE.
export const reservationTabs: ReservationTab[] = [
  { id: 'compliance-legal', labelKey: 'compliance:legal.tab', order: 50, permission: 'compliance.view', Component: LegalTabLazy },
]
