import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `calendar` feature with placeholder pages. Owner: C13 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'calendar', element: <UnderConstruction titleKey="calendar:nav.calendar" /> },
  ],
}
