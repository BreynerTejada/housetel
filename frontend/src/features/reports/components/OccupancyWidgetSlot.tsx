import { lazy, Suspense } from 'react'

// The widget body (and Recharts) load lazily, so the Today page only downloads them when the widget shows.
const OccupancyWidget = lazy(() => import('./OccupancyWidget'))

export function OccupancyWidgetSlot() {
  return (
    <Suspense fallback={<div aria-hidden className="h-52 animate-shimmer rounded-lg border border-border bg-surface-2" />}>
      <OccupancyWidget />
    </Suspense>
  )
}
