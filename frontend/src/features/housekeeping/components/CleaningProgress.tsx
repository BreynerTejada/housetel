import { lazy, Suspense } from 'react'

// Loaded only when the Today panel renders it (widgets.tsx is imported eagerly by the extension registry).
const CleaningProgressWidget = lazy(() => import('./CleaningProgressWidget'))

/** Today panel widget: the day's cleaning progress (lazy body with a quiet placeholder). */
export function CleaningProgress() {
  return (
    <Suspense fallback={<div className="min-h-40 rounded-xl border border-border bg-surface" />}>
      <CleaningProgressWidget />
    </Suspense>
  )
}
