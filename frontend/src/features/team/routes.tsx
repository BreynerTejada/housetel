import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `team` feature with placeholder pages. Owner: B3 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  public: [
    { path: '/invite/:token', element: <UnderConstruction titleKey="team:pages.invite" /> },
  ],
  app: [
    { path: 'settings/users', element: <UnderConstruction titleKey="team:nav.users" /> },
    { path: 'settings/roles', element: <UnderConstruction titleKey="team:nav.roles" /> },
  ],
}
