import type { FeatureRoutes } from '@/app/extensions'

// Owner: C12. Control center: alert center, integrations (real / simulated), automations and the audit log.
export const routes: FeatureRoutes = {
  app: [
    { path: 'alerts', lazy: () => import('./pages/AlertsPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/integrations', lazy: () => import('./pages/IntegrationsPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/automations', lazy: () => import('./pages/AutomationsPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/audit', lazy: () => import('./pages/AuditPage').then((m) => ({ Component: m.default })) },
  ],
}
