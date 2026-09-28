import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

// The reservation tab file is imported eagerly by the app shell: it points here and the real component loads on
// demand, so the corporate code stays out of the main bundle.
const BillingTab = lazy(() => import('./BillingTab').then((module) => ({ default: module.BillingTab })))

export function BillingTabLazy({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
      <BillingTab reservationId={reservationId} />
    </Suspense>
  )
}
