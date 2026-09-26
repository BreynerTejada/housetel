import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `messaging` feature with placeholder pages. Owner: C6 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'inbox', element: <UnderConstruction titleKey="messaging:nav.inbox" /> },
    { path: 'simulators/whatsapp', element: <UnderConstruction titleKey="messaging:nav.waSim" /> },
    { path: 'settings/messaging', element: <UnderConstruction titleKey="messaging:nav.settingsMessaging" /> },
  ],
}
