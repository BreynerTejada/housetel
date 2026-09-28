import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `calendar` feature (owner: C13). Pages load lazily so other bundles never carry the grid.
export const routes: FeatureRoutes = {
  app: [{ path: 'calendar', lazy: () => import('./pages/CalendarPage').then((m) => ({ Component: m.default })) }],
}
