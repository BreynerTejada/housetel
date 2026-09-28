import type { FeatureRoutes } from '@/app/extensions'

// Routes of the `ai` feature (plan C9 · §E). Pages load lazily.
export const routes: FeatureRoutes = {
  app: [
    { path: 'onboarding', lazy: () => import('./pages/OnboardingPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/chatbot', lazy: () => import('./pages/ChatbotSettingsPage').then((m) => ({ Component: m.default })) },
    { path: 'settings/ai', lazy: () => import('./pages/AISettingsPage').then((m) => ({ Component: m.default })) },
  ],
}
