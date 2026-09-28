import type { FeatureRoutes } from '@/app/extensions'

// Team (B3): users and roles of the organization, and the public page that accepts an invitation.
// Account security (P2): forgot / reset password, email verification and "My account and security".
// The token params are not called `token` on purpose: PublicLayout hands a `token` param to the chat widget
// as a guest-portal token, and these secrets must not travel to other endpoints.
// Pages load lazily so other bundles never carry this code.
export const routes: FeatureRoutes = {
  public: [
    { path: '/invite/:token', lazy: () => import('./pages/InvitePage').then((m) => ({ Component: m.default })) },
    { path: '/forgot-password', lazy: () => import('./pages/ForgotPasswordPage').then((m) => ({ Component: m.default })) },
    {
      path: '/reset-password/:uid/:resetToken',
      lazy: () => import('./pages/ResetPasswordPage').then((m) => ({ Component: m.default })),
    },
    { path: '/verify-email/:verifyToken', lazy: () => import('./pages/VerifyEmailPage').then((m) => ({ Component: m.default })) },
  ],
  app: [
    { path: 'settings/account', lazy: () => import('./pages/AccountPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/users', lazy: () => import('./pages/UsersPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/roles', lazy: () => import('./pages/RolesPage').then((m) => ({ Component: m.default })) },
  ],
  // Platform super-admins have no hotel (the /app shell shows "no properties"): same page in their own area.
  admin: [{ path: 'account', lazy: () => import('./pages/AccountPage').then((m) => ({ Component: m.default })) }],
}
