import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `saas` feature (plan §E, owner C11). Pages load lazily.
export const routes: FeatureRoutes = {
  public: [
    { path: '/signup', lazy: () => import('./pages/SignupPage').then((m) => ({ Component: m.default })) },
    // Terms, personal data policy and data processing agreement (plan P6); `/legal` opens the terms.
    { path: '/legal', lazy: () => import('./pages/LegalPage').then((m) => ({ Component: m.default })) },
    { path: '/legal/:doc', lazy: () => import('./pages/LegalPage').then((m) => ({ Component: m.default })) },
  ],
  app: [
    {
      path: 'getting-started',
      lazy: () => import('./pages/GettingStartedPage').then((m) => ({ Component: m.default })),
    },
    { path: 'settings/billing', lazy: () => import('./pages/BillingPage').then((m) => ({ Component: m.default })) },
  ],
  admin: [
    { index: true, lazy: () => import('./pages/admin/AdminHomePage').then((m) => ({ Component: m.default })) },
    {
      path: 'organizations',
      lazy: () => import('./pages/admin/OrganizationsPage').then((m) => ({ Component: m.default })),
    },
    {
      path: 'organizations/:id',
      lazy: () => import('./pages/admin/OrganizationDetailPage').then((m) => ({ Component: m.default })),
    },
    { path: 'plans', lazy: () => import('./pages/admin/PlansPage').then((m) => ({ Component: m.default })) },
    { path: 'billing', lazy: () => import('./pages/admin/AdminBillingPage').then((m) => ({ Component: m.default })) },
    {
      path: 'commissions',
      lazy: () => import('./pages/admin/CommissionsPage').then((m) => ({ Component: m.default })),
    },
  ],
}
