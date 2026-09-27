import type { FeatureRoutes } from '@/app/extensions'

// Team (B3): users and roles of the organization, and the public page that accepts an invitation.
// Pages load lazily so other bundles never carry this code.
export const routes: FeatureRoutes = {
  public: [{ path: '/invite/:token', lazy: () => import('./pages/InvitePage').then((m) => ({ Component: m.default })) }],
  app: [
    { path: 'settings/users', lazy: () => import('./pages/UsersPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/roles', lazy: () => import('./pages/RolesPage').then((m) => ({ Component: m.default })) },
  ],
}
