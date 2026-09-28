import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Crown, Smartphone } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { getArrivalsCheckins, getServiceRequests, portalKeys, type CheckinStatus } from '../../api'

const TONE: Record<CheckinStatus, BadgeTone> = { completed: 'success', in_progress: 'warning', not_started: 'neutral' }
const PENDING = { status: ['requested' as const], page_size: 20 }

/** Today panel widget: today's arrivals and whether each one already checked in online. */
export function OnlineCheckinWidget() {
  const { t } = useTranslation('guestportal')
  const titleId = useId()
  const arrivals = useQuery({ queryKey: portalKeys.arrivals(), queryFn: () => getArrivalsCheckins() })
  const requests = useQuery({ queryKey: portalKeys.requests(PENDING), queryFn: () => getServiceRequests(PENDING) })
  const rows = arrivals.data ?? []
  const done = rows.filter((row) => row.checkin_status === 'completed').length
  const pending = requests.data?.count ?? 0
  const firstPending = requests.data?.results[0]

  return (
    <section aria-labelledby={titleId} className="grid gap-3 rounded-xl border border-border bg-surface p-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id={titleId} className="flex items-center gap-2 text-[15px] font-bold">
            <Smartphone aria-hidden className="size-4 text-muted" />
            {t('widget.title')}
          </h2>
          {rows.length > 0 && <p className="text-[13px] text-muted">{t('widget.progress', { done, total: rows.length })}</p>}
        </div>
        {rows.length > 0 && (
          <span className="num text-[22px] leading-7 font-bold tracking-[-0.03em]">
            {done}
            <span className="text-[15px] text-muted">/{rows.length}</span>
          </span>
        )}
      </header>

      {arrivals.isPending ? (
        <div className="grid gap-2">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : arrivals.isError ? (
        <ErrorState error={arrivals.error} onRetry={() => arrivals.refetch()} className="py-6" />
      ) : rows.length === 0 ? (
        <p className="py-3 text-sm text-muted">{t('widget.empty')}</p>
      ) : (
        <>
          <div aria-hidden className="h-1.5 overflow-hidden rounded-full bg-surface-3">
            <div className="h-full rounded-full bg-success" style={{ width: `${(done / rows.length) * 100}%` }} />
          </div>
          <ul className="-mx-1 grid">
            {rows.map((row) => (
              <li key={row.reservation_id}>
                <Link
                  to={`/app/reservations/${row.reservation_id}`}
                  className="flex items-center gap-3 rounded-lg px-1 py-2 transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 truncate text-sm font-semibold">
                      {row.is_vip && <Crown aria-label={t('widget.vip')} className="size-3.5 shrink-0 text-warning" />}
                      {row.guest_name}
                    </span>
                    <span className="num block text-[12px] text-muted">
                      {row.code}
                      {row.eta ? ` · ${row.eta}` : ''}
                    </span>
                  </span>
                  <Badge tone={TONE[row.checkin_status]}>{t(`staff.status.${row.checkin_status}`)}</Badge>
                  <ChevronRight aria-hidden className="size-4 shrink-0 text-subtle" />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      {pending > 0 && firstPending && (
        <Link
          to={`/app/reservations/${firstPending.reservation.id}`}
          className="flex items-center justify-between gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm font-semibold text-warning-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
        >
          {t('widget.requests', { count: pending })}
          <ChevronRight aria-hidden className="size-4" />
        </Link>
      )}
    </section>
  )
}
