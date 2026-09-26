import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `housekeeping` feature with placeholder pages. Owner: C2 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'housekeeping', element: <UnderConstruction titleKey="housekeeping:nav.housekeeping" /> },
    { path: 'housekeeping/mine', element: <UnderConstruction titleKey="housekeeping:pages.mine" /> },
    { path: 'maintenance', element: <UnderConstruction titleKey="housekeeping:nav.maintenance" /> },
    { path: 'settings/housekeeping', element: <UnderConstruction titleKey="housekeeping:nav.settingsHousekeeping" /> },
  ],
}
