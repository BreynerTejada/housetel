import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `finance` feature with placeholder pages. Owner: B4 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  bare: [
    { path: '/sim/pay/:reference', element: <UnderConstruction titleKey="finance:pages.simPay" /> },
  ],
  app: [
    { path: 'cashier', element: <UnderConstruction titleKey="finance:nav.cashier" /> },
  ],
}
