import type { ReservationTab } from '@/app/extensions'
import { FolioTab } from './components/FolioTab'

// Owner: B4. The reservation detail (C1) renders these tabs through `useReservationTabs()`.
export const reservationTabs: ReservationTab[] = [
  { id: 'folio', labelKey: 'finance:tabs.folio', order: 20, permission: 'finance.view', Component: FolioTab },
]
