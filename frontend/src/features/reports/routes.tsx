import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `reports` feature (plan §E, owner C10). Pages load lazily.
export const routes: FeatureRoutes = {
  app: [
    { path: 'reports', lazy: () => import('./pages/ReportsHubPage').then((m) => ({ Component: m.default })) },
    { path: 'reports/:reportId', lazy: () => import('./pages/ReportPage').then((m) => ({ Component: m.default })) },
  ],
}
