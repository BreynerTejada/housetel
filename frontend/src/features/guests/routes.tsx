import type { FeatureRoutes } from '@/app/extensions'

// Guests CRM (B3). Pages load lazily so other bundles never carry this code.
export const routes: FeatureRoutes = {
  app: [
    { path: 'guests', lazy: () => import('./pages/GuestsPage').then((m) => ({ Component: m.default })) },
    { path: 'guests/:id', lazy: () => import('./pages/GuestDetailPage').then((m) => ({ Component: m.default })) },
  ],
}
