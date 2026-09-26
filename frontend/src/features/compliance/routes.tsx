import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `compliance` feature with placeholder pages. Owner: C7 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'compliance', element: <UnderConstruction titleKey="compliance:nav.compliance" /> },
    { path: 'settings/compliance', element: <UnderConstruction titleKey="compliance:nav.settingsCompliance" /> },
  ],
}
