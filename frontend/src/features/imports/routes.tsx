import type { FeatureRoutes } from '@/app/extensions'

// Owner: P5. `/app/settings/import` (new import + history) and one page per job (map → review → import →
// result). Pages load on demand (plan §E).
export const routes: FeatureRoutes = {
  app: [
    { path: 'settings/import', lazy: () => import('./pages/ImportPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/import/:jobId', lazy: () => import('./pages/ImportJobPage').then((m) => ({ Component: m.default })) },
  ],
}
