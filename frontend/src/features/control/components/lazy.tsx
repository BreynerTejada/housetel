import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

// Extension files (widget, reservation tab) are imported eagerly by the app shell: they point here and the real
// components load on demand, so the control center's code stays out of the main bundle.
const AlertsWidget = lazy(() => import('./AlertsWidget'))
const ReservationHistoryTab = lazy(() => import('./ReservationHistoryTab'))

export function AlertsWidgetLazy() {
  return (
    <Suspense fallback={<div className="min-h-40 rounded-xl border border-border bg-surface" />}>
      <AlertsWidget />
    </Suspense>
  )
}

export function ReservationHistoryTabLazy({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
      <ReservationHistoryTab reservationId={reservationId} />
    </Suspense>
  )
}
