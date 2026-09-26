import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `rates` feature with placeholder pages. Owner: B2a replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'rates', element: <UnderConstruction titleKey="rates:nav.rates" /> },
    { path: 'rates/plans', element: <UnderConstruction titleKey="rates:nav.ratePlans" /> },
    { path: 'rates/promos', element: <UnderConstruction titleKey="rates:nav.promos" /> },
    { path: 'settings/taxes', element: <UnderConstruction titleKey="rates:nav.taxes" /> },
    { path: 'settings/policies', element: <UnderConstruction titleKey="rates:nav.policies" /> },
    { path: 'settings/extras', element: <UnderConstruction titleKey="rates:nav.extras" /> },
  ],
}
