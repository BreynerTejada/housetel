import { ArrowRight, CircleCheck } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { formatNumber, formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAlertCount, type Severity } from '../api'
import { SeverityDot, SeverityIcon } from './severity'

const SHOWN = 4
const SEVERITIES: Severity[] = ['critical', 'warning', 'info']

/** Today panel (C1): the hotel's open alerts — counts by severity and the most severe ones, each a link to fix it. */
export default function AlertsWidget() {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const id = useId()
  const query = useAlertCount()

  return (
    <section aria-labelledby={id} className="grid h-full content-start gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {t('widget.title')}
        </h2>
        <Link to="/app/alerts" className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
          {t('widget.open')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </div>
      {query.isPending ? (
        <LoadingState variant="rows" rows={3} className="p-0" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} className="py-6" />
      ) : query.data.open === 0 ? (
        <p className="flex items-center gap-2 text-sm text-success-ink">
          <CircleCheck aria-hidden className="size-4" />
          {t('widget.allClear')}
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-2">
            {SEVERITIES.map((severity) => {
              const count = query.data.by_severity[severity]
              return (
                <div key={severity} className={cn('rounded-lg border border-border px-2.5 py-2', count === 0 && 'opacity-60')}>
                  <dt className="flex items-center gap-1.5 text-2xs font-semibold text-muted">
                    <SeverityDot severity={severity} />
                    <span className="truncate">{t(`severityPlural.${severity}`)}</span>
                  </dt>
                  <dd className="num mt-0.5 text-lg leading-6 font-bold text-fg">{formatNumber(count, lang, 0)}</dd>
                </div>
              )
            })}
          </dl>
          <ul className="grid gap-0.5">
            {query.data.latest.slice(0, SHOWN).map((alert) => (
              <li key={alert.id}>
                <Link
                  to={alert.link || '/app/alerts'}
                  className="flex items-start gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                >
                  <SeverityIcon severity={alert.severity} className="mt-0.5" />
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 text-sm text-fg">{alert.title}</span>
                    <span className="block text-xs text-muted">{formatRelative(alert.updated_at, lang)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {query.data.open > SHOWN && (
            <p className="px-2 text-xs text-muted">{t('widget.more', { count: query.data.open - Math.min(SHOWN, query.data.latest.length) })}</p>
          )}
        </>
      )}
    </section>
  )
}
