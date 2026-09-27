import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `rates` feature (plan §E). Pages load lazily so other bundles never carry the rates code.
export const routes: FeatureRoutes = {
  app: [
    { path: 'rates', lazy: () => import('./pages/RatesGridPage').then((m) => ({ Component: m.default })) },
    { path: 'rates/plans', lazy: () => import('./pages/PlansPage').then((m) => ({ Component: m.default })) },
    { path: 'rates/promos', lazy: () => import('./pages/PromosPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/taxes', lazy: () => import('./pages/TaxesPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/policies', lazy: () => import('./pages/PoliciesPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/extras', lazy: () => import('./pages/ExtrasPage').then((m) => ({ Component: m.default })) },
  ],
}
