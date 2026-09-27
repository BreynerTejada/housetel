import type { FeatureRoutes } from '@/app/extensions'

// Owner: B4. `/app/cashier` (staff) and the simulated payment gateway `/sim/pay/:reference` (bare page).
export const routes: FeatureRoutes = {
  bare: [
    { path: '/sim/pay/:reference', lazy: () => import('./pages/SimPayPage').then((m) => ({ Component: m.default })) },
  ],
  app: [{ path: 'cashier', lazy: () => import('./pages/CashierPage').then((m) => ({ Component: m.default })) }],
}
