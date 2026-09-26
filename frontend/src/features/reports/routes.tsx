import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `reports` feature with placeholder pages. Owner: C10 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'reports', element: <UnderConstruction titleKey="reports:nav.reports" /> },
    { path: 'reports/:reportId', element: <UnderConstruction titleKey="reports:pages.reportDetail" /> },
  ],
}
