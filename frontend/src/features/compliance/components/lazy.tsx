import { lazy, Suspense } from 'react'
import { LoadingState } from '@/components/LoadingState'

// Extension files (tab, action, widget) are imported eagerly by the app shell: they point here and the real
// components load on demand, so compliance code stays out of the main bundle.
const ReservationLegalTab = lazy(() => import('./ReservationLegalTab').then((module) => ({ default: module.ReservationLegalTab })))
const IssueInvoicePanel = lazy(() => import('./IssueInvoicePanel').then((module) => ({ default: module.IssueInvoicePanel })))
const LegalWidget = lazy(() => import('./LegalWidget'))

export function LegalTabLazy({ reservationId }: { reservationId: string }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
      <ReservationLegalTab reservationId={reservationId} />
    </Suspense>
  )
}

/** Reservation action "Emitir factura": the reservation detail (C1) draws the dialog and its title around it. */
export function IssueInvoiceActionLazy({ reservationId, close }: { reservationId: string; close: () => void }) {
  return (
    <Suspense fallback={<LoadingState variant="rows" rows={3} className="p-0" />}>
      <IssueInvoicePanel reservationId={reservationId} onClose={close} />
    </Suspense>
  )
}

export function LegalWidgetLazy() {
  return (
    <Suspense fallback={<div className="min-h-40 rounded-xl border border-border bg-surface" />}>
      <LegalWidget />
    </Suspense>
  )
}
