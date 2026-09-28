import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

const GuestMessagesPanel = lazy(() => import('./GuestMessagesPanel'))

/** Reservation detail tab "Messages" (C1 renders it): loaded on demand, outside the main bundle. */
export function ReservationMessagesTab({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={3} />}>
      <GuestMessagesPanel reservationId={reservationId} />
    </Suspense>
  )
}

/** Guest profile tab "Messages" (B3 renders it). */
export function GuestMessagesTab({ guestId }: { guestId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={3} />}>
      <GuestMessagesPanel guestId={guestId} />
    </Suspense>
  )
}
