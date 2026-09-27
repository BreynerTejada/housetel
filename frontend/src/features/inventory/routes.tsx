import type { FeatureRoutes } from '@/app/extensions'

// Inventory settings (plan §E, owner B1). Pages load lazily; `settings/*` routes nest in SettingsLayout.
export const routes: FeatureRoutes = {
  app: [
    { path: 'settings/property', lazy: () => import('./pages/PropertyPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/room-types', lazy: () => import('./pages/RoomTypesPage').then((m) => ({ Component: m.default })) },
    {
      path: 'settings/room-types/:roomTypeId',
      lazy: () => import('./pages/RoomTypeEditorPage').then((m) => ({ Component: m.default })),
    },
    { path: 'settings/rooms', lazy: () => import('./pages/RoomsPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/rooms/:roomId', lazy: () => import('./pages/RoomEditorPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/custom-fields', lazy: () => import('./pages/CustomFieldsPage').then((m) => ({ Component: m.default })) },
  ],
}
