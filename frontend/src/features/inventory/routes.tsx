import type { FeatureRoutes } from '@/app/extensions'
import { UnderConstruction } from '@/components/UnderConstruction'

// Phase A stub: routes of the `inventory` feature with placeholder pages. Owner: B1 replaces them
// (keep the paths; pages load with `lazy`). See docs/integration-notes/A2-frontend-foundation.md.
export const routes: FeatureRoutes = {
  app: [
    { path: 'settings/property', element: <UnderConstruction titleKey="inventory:nav.property" /> },
    { path: 'settings/room-types', element: <UnderConstruction titleKey="inventory:nav.roomTypes" /> },
    { path: 'settings/rooms', element: <UnderConstruction titleKey="inventory:nav.rooms" /> },
    { path: 'settings/custom-fields', element: <UnderConstruction titleKey="inventory:nav.customFields" /> },
  ],
}
