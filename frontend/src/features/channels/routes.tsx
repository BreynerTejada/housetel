import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `channels` feature (plan §E, owner C3). Pages load lazily so other bundles never carry them.
export const routes: FeatureRoutes = {
  app: [
    { path: 'channels', lazy: () => import('./pages/ChannelsPage').then((m) => ({ Component: m.default })) },
    { path: 'simulators/ota', lazy: () => import('./pages/OtaSimulatorPage').then((m) => ({ Component: m.default })) },
  ],
}
