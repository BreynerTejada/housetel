import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `saas` feature with placeholder pages. Owner: C11 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  public: [
    { path: '/signup', element: <UnderConstruction titleKey="saas:pages.signup" /> },
  ],
  app: [
    { path: 'getting-started', element: <UnderConstruction titleKey="saas:nav.gettingStarted" /> },
    { path: 'settings/billing', element: <UnderConstruction titleKey="saas:nav.billing" /> },
  ],
  admin: [
    { index: true, element: <UnderConstruction titleKey="saas:nav.adminHome" /> },
    { path: 'organizations', element: <UnderConstruction titleKey="saas:nav.adminOrgs" /> },
    { path: 'organizations/:id', element: <UnderConstruction titleKey="saas:pages.adminOrgDetail" /> },
    { path: 'plans', element: <UnderConstruction titleKey="saas:nav.adminPlans" /> },
    { path: 'billing', element: <UnderConstruction titleKey="saas:nav.adminBilling" /> },
    { path: 'commissions', element: <UnderConstruction titleKey="saas:nav.adminCommissions" /> },
  ],
}
