import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `marketplace` feature (plan §E, owner C4). Pages load lazily, so the staff shell never ships
// with the marketplace and the other way around. Hotel-branded pages (`/h/:slug…`) hide Housetel's chrome.
const HOTEL_BRANDED = { chrome: 'none' } as const

export const routes: FeatureRoutes = {
  public: [
    { path: '/', lazy: () => import('./pages/HomePage').then((m) => ({ Component: m.default })) },
    { path: '/search', lazy: () => import('./pages/SearchPage').then((m) => ({ Component: m.default })) },
    { path: '/hotel/:slug', lazy: () => import('./pages/HotelPage').then((m) => ({ Component: m.default })) },
    { path: '/book/:slug', lazy: () => import('./pages/CheckoutPage').then((m) => ({ Component: m.default })) },
    { path: '/booking/:code/confirmed', lazy: () => import('./pages/ConfirmationPage').then((m) => ({ Component: m.default })) },
    { path: '/h/:slug', handle: HOTEL_BRANDED, lazy: () => import('./pages/EnginePage').then((m) => ({ Component: m.default })) },
    {
      path: '/h/:slug/book',
      handle: HOTEL_BRANDED,
      lazy: () => import('./pages/EngineCheckoutPage').then((m) => ({ Component: m.default })),
    },
    {
      path: '/h/:slug/booking/:code',
      handle: HOTEL_BRANDED,
      lazy: () => import('./pages/EngineConfirmationPage').then((m) => ({ Component: m.default })),
    },
  ],
  bare: [{ path: '/embed/:slug', lazy: () => import('./pages/EmbedPage').then((m) => ({ Component: m.default })) }],
  app: [
    {
      path: 'settings/booking-engine',
      lazy: () => import('./pages/BookingEngineSettingsPage').then((m) => ({ Component: m.default })),
    },
  ],
}
