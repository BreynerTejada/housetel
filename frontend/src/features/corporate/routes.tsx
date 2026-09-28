import type { FeatureRoutes } from '@/app/extensions'

// Owner: P4. Pages load on demand (plan §E).
export const routes: FeatureRoutes = {
  app: [
    { path: 'companies', lazy: () => import('./pages/CompaniesPage').then((m) => ({ Component: m.default })) },
    { path: 'companies/:id', lazy: () => import('./pages/CompanyDetailPage').then((m) => ({ Component: m.default })) },
    { path: 'receivables', lazy: () => import('./pages/ReceivablesPage').then((m) => ({ Component: m.default })) },
  ],
}
