import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

const FolioPanel = lazy(() => import('./FolioPanel'))

/** Reservation detail tab "Folio": the folio panel, loaded on demand (its code is not in the main bundle). */
export function FolioTab({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
      <FolioPanel reservationId={reservationId} />
    </Suspense>
  )
}
