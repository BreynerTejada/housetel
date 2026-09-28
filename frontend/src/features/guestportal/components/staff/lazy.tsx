import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

// Extension files (tabs, actions, widgets) are imported eagerly by the app shell: they point here, and the
// real components load on demand so their code stays out of the main bundle.
const CheckinTab = lazy(() => import('./ReservationTabs').then((module) => ({ default: module.CheckinTab })))
const RequestsTab = lazy(() => import('./ReservationTabs').then((module) => ({ default: module.RequestsTab })))
const SendLinkAction = lazy(() => import('./LinkActions').then((module) => ({ default: module.SendLinkAction })))
const LinkQrAction = lazy(() => import('./LinkActions').then((module) => ({ default: module.LinkQrAction })))
const OnlineCheckinWidget = lazy(() => import('./OnlineCheckinWidget').then((module) => ({ default: module.OnlineCheckinWidget })))

export function CheckinTabLazy({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
      <CheckinTab reservationId={reservationId} />
    </Suspense>
  )
}

export function RequestsTabLazy({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={3} />}>
      <RequestsTab reservationId={reservationId} />
    </Suspense>
  )
}

export function SendLinkActionLazy({ reservationId, close }: { reservationId: string; close: () => void }) {
  return (
    <Suspense fallback={null}>
      <SendLinkAction reservationId={reservationId} close={close} />
    </Suspense>
  )
}

export function LinkQrActionLazy({ reservationId, close }: { reservationId: string; close: () => void }) {
  return (
    <Suspense fallback={null}>
      <LinkQrAction reservationId={reservationId} close={close} />
    </Suspense>
  )
}

export function OnlineCheckinWidgetLazy() {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={3} />}>
      <OnlineCheckinWidget />
    </Suspense>
  )
}
