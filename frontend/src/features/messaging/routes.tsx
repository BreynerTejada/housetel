import type { FeatureRoutes } from '@/app/extensions'

// Owner: C6. Inbox, the WhatsApp simulator and the messaging settings (templates + automatic messages).
export const routes: FeatureRoutes = {
  app: [
    { path: 'inbox', lazy: () => import('./pages/InboxPage').then((m) => ({ Component: m.default })) },
    {
      path: 'simulators/whatsapp',
      lazy: () => import('./pages/WhatsAppSimulatorPage').then((m) => ({ Component: m.default })),
    },
    {
      path: 'settings/messaging',
      lazy: () => import('./pages/MessagingSettingsPage').then((m) => ({ Component: m.default })),
    },
  ],
}
