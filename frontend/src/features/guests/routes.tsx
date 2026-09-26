import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `guests` feature with placeholder pages. Owner: B3 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'guests', element: <UnderConstruction titleKey="guests:nav.guests" /> },
    { path: 'guests/:id', element: <UnderConstruction titleKey="guests:pages.guestDetail" /> },
  ],
}
