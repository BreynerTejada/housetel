import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `ai` feature with placeholder pages. Owner: C9 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'onboarding', element: <UnderConstruction titleKey="ai:nav.onboarding" /> },
    { path: 'settings/chatbot', element: <UnderConstruction titleKey="ai:nav.chatbot" /> },
    { path: 'settings/ai', element: <UnderConstruction titleKey="ai:nav.aiSettings" /> },
  ],
}
