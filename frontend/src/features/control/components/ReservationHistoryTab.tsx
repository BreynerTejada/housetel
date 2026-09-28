import { ArrowUpRight, FileClock } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { useCan } from '@/lib/permissions'
import { useAuditEvents } from '../api'
import { AuditEventSheet } from './AuditEventSheet'
import { AuditTimeline } from './AuditTimeline'

/**
 * Reservation detail tab "Historial": every audited change of the reservation, its stays, folios, charges,
 * payments and related records (online check-in, invoices…), with undo for what can be reverted.
 */
export default function ReservationHistoryTab({ reservationId }: { reservationId: string }) {
  const { t } = useTranslation('control')
  const canUndo = useCan('control.audit_undo')
  const filters = useMemo(() => ({ reservation: reservationId }), [reservationId])
  const events = useAuditEvents(filters, { pageSize: 30 })
  const [openId, setOpenId] = useState<string | null>(null)
  const items = useMemo(() => events.data?.pages.flatMap((page) => page.results) ?? [], [events.data])

  return (
    <div className="grid min-w-0 gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-bold text-fg">{t('history.title')}</h2>
          <p className="max-w-2xl text-[13px] text-muted">{t('history.description')}</p>
        </div>
        <Link
          to={`/app/settings/audit?reservation=${reservationId}`}
          className="inline-flex items-center gap-1 rounded-sm text-[13px] font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
        >
          {t('history.openLog')}
          <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      </div>

      {events.isPending ? (
        <LoadingState variant="rows" rows={5} className="p-0" />
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => void events.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={FileClock} title={t('history.empty')} />
      ) : (
        <>
          <AuditTimeline events={items} onOpen={setOpenId} canUndo={canUndo} hideLinks selectedId={openId} />
          {events.hasNextPage && (
            <div className="flex justify-center">
              <Button size="sm" onClick={() => void events.fetchNextPage()} loading={events.isFetchingNextPage}>
                {events.isFetchingNextPage ? t('common.loadingMore') : t('common.loadMore')}
              </Button>
            </div>
          )}
        </>
      )}

      <AuditEventSheet eventId={openId} onOpenChange={(open) => !open && setOpenId(null)} onNavigate={setOpenId} hideLinks />
    </div>
  )
}
