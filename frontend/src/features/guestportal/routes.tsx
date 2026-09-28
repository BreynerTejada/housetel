import type { FeatureRoutes } from '@/app/extensions'

// Owner: C5. Hotel-branded guest pages hide the Housetel header/footer (`chrome: 'none'`); the public layout
// still mounts the chat bubble with the portal token.
export const routes: FeatureRoutes = {
  public: [
    { path: '/g/:token', handle: { chrome: 'none' }, lazy: () => import('./pages/PortalPage').then((m) => ({ Component: m.default })) },
    { path: '/g/:token/checkin', handle: { chrome: 'none' }, lazy: () => import('./pages/CheckinPage').then((m) => ({ Component: m.default })) },
  ],
  app: [{ path: 'settings/guest-portal', lazy: () => import('./pages/SettingsPage').then((m) => ({ Component: m.default })) }],
}
