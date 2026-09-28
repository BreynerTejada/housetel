import type { FeatureRoutes } from '@/app/extensions'

// Owner: C7. Pages load on demand (plan §E).
export const routes: FeatureRoutes = {
  app: [
    { path: 'compliance', lazy: () => import('./pages/CompliancePage').then((m) => ({ Component: m.default })) },
    { path: 'settings/compliance', lazy: () => import('./pages/ComplianceSettingsPage').then((m) => ({ Component: m.default })) },
  ],
}
