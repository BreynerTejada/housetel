import type { FeatureRoutes } from '@/app/extensions'

// Pages load lazily (the public bundle never pulls housekeeping code). Paths fixed by plan §E.
export const routes: FeatureRoutes = {
  app: [
    { path: 'housekeeping', lazy: () => import('./pages/BoardPage').then((m) => ({ Component: m.default })) },
    { path: 'housekeeping/mine', lazy: () => import('./pages/MyRoomsPage').then((m) => ({ Component: m.default })) },
    { path: 'maintenance', lazy: () => import('./pages/MaintenancePage').then((m) => ({ Component: m.default })) },
    { path: 'settings/housekeeping', lazy: () => import('./pages/SettingsPage').then((m) => ({ Component: m.default })) },
  ],
}
