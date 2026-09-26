import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `frontdesk` feature with placeholder pages. Owner: C1 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { index: true, element: <UnderConstruction titleKey="frontdesk:nav.today" /> },
    { path: 'reservations', element: <UnderConstruction titleKey="frontdesk:nav.reservations" /> },
    { path: 'reservations/new', element: <UnderConstruction titleKey="frontdesk:pages.newReservation" /> },
    { path: 'reservations/:id', element: <UnderConstruction titleKey="frontdesk:pages.reservationDetail" /> },
    { path: 'night-audit', element: <UnderConstruction titleKey="frontdesk:nav.nightAudit" /> },
  ],
}
