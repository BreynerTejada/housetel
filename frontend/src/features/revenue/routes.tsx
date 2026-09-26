import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `revenue` feature with placeholder pages. Owner: C8 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'revenue', element: <UnderConstruction titleKey="revenue:nav.revenue" /> },
  ],
}
