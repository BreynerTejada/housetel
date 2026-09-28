import { lazy, Suspense } from 'react'

// The widget body loads lazily, so the Today page only downloads it when it is shown.
const RecommendationsWidget = lazy(() => import('./RecommendationsWidget'))

export function RecommendationsWidgetSlot() {
  return (
    <Suspense fallback={<div aria-hidden className="h-40 animate-shimmer rounded-lg border border-border bg-surface-2" />}>
      <RecommendationsWidget />
    </Suspense>
  )
}
