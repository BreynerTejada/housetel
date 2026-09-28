import type { FeatureRoutes } from '@/app/extensions'

// Front desk (plan C1 · §E): Today is the home of /app; reservations list, wizard and detail; night audit;
// groups with their allotments and rooming list (pilot P3).
export const routes: FeatureRoutes = {
  app: [
    { index: true, lazy: () => import('./pages/TodayPage').then((m) => ({ Component: m.default })) },
    { path: 'reservations', lazy: () => import('./pages/ReservationsPage').then((m) => ({ Component: m.default })) },
    { path: 'reservations/new', lazy: () => import('./pages/NewReservationPage').then((m) => ({ Component: m.default })) },
    { path: 'reservations/:id', lazy: () => import('./pages/ReservationDetailPage').then((m) => ({ Component: m.default })) },
    { path: 'groups', lazy: () => import('./pages/GroupsPage').then((m) => ({ Component: m.default })) },
    { path: 'groups/:id', lazy: () => import('./pages/GroupDetailPage').then((m) => ({ Component: m.default })) },
    { path: 'night-audit', lazy: () => import('./pages/NightAuditPage').then((m) => ({ Component: m.default })) },
  ],
}
