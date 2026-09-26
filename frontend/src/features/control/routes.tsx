import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `control` feature with placeholder pages. Owner: C12 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'alerts', element: <UnderConstruction titleKey="control:nav.alerts" /> },
    { path: 'settings/integrations', element: <UnderConstruction titleKey="control:nav.integrations" /> },
    { path: 'settings/automations', element: <UnderConstruction titleKey="control:nav.automations" /> },
    { path: 'settings/audit', element: <UnderConstruction titleKey="control:nav.audit" /> },
  ],
}
