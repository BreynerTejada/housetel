import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `guestportal` feature with placeholder pages. Owner: C5 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  public: [
    { path: '/g/:token', handle: { chrome: 'none' }, element: <UnderConstruction titleKey="guestportal:pages.portal" /> },
    { path: '/g/:token/checkin', handle: { chrome: 'none' }, element: <UnderConstruction titleKey="guestportal:pages.checkin" /> },
  ],
  app: [
    { path: 'settings/guest-portal', element: <UnderConstruction titleKey="guestportal:nav.guestPortal" /> },
  ],
}
