import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `marketplace` feature with placeholder pages. Owner: C4 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  public: [
    { path: '/', lazy: () => import('./pages/HomePage').then((m) => ({ Component: m.default })) },
    { path: '/search', element: <UnderConstruction titleKey="marketplace:pages.search" /> },
    { path: '/hotel/:slug', element: <UnderConstruction titleKey="marketplace:pages.hotel" /> },
    { path: '/book/:slug', element: <UnderConstruction titleKey="marketplace:pages.book" /> },
    { path: '/booking/:code/confirmed', element: <UnderConstruction titleKey="marketplace:pages.confirmed" /> },
    { path: '/h/:slug', handle: { chrome: 'none' }, element: <UnderConstruction titleKey="marketplace:pages.engine" /> },
  ],
  bare: [
    { path: '/embed/:slug', element: <UnderConstruction titleKey="marketplace:pages.embed" /> },
  ],
  app: [
    { path: 'settings/booking-engine', element: <UnderConstruction titleKey="marketplace:nav.bookingEngine" /> },
  ],
}
