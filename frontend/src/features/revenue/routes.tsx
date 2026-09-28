import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `revenue` feature (plan §E, owner C8). The page loads lazily.
export const routes: FeatureRoutes = {
  app: [{ path: 'revenue', lazy: () => import('./pages/RevenuePage').then((m) => ({ Component: m.default })) }],
}
