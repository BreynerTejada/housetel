import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `channels` feature with placeholder pages. Owner: C3 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'channels', element: <UnderConstruction titleKey="channels:nav.channels" /> },
    { path: 'simulators/ota', element: <UnderConstruction titleKey="channels:nav.otaSim" /> },
  ],
}
