import { ArrowRight, Check, TrendingUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useDecision, useRevenueSummary, useUpcomingRecommendations } from '../api'
import { pick, signedPercent } from '../lib/format'
import { shortDate } from '../lib/labels'
import { STEP_CLASS, stepOf } from '../lib/scale'

/** Today panel: the next nights whose price should move, approved in one click. */
export default function RecommendationsWidget() {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const canManage = useCan('revenue.manage')
  const summary = useRevenueSummary()
  const upcoming = useUpcomingRecommendations(property?.business_date ?? '')
  const decision = useDecision()
  const items = upcoming.data?.results ?? []
  const currency = summary.data?.currency ?? property?.currency ?? 'COP'

  function approve(ids: string[]) {
    decision.mutate(
      { decision: 'approve', ids },
      {
        onSuccess: (result) => {
          const done = result.recommendations.filter((rec) => rec.status === 'applied').length
          if (done) toast.success(t('decide.done.approve', { count: done }))
          if (result.errors.length) toast.error(t('decide.errors', { count: result.errors.length, detail: result.errors[0].detail }))
        },
        onError: (error) => toast.error(errorMessage(error, t)),
      },
    )
  }

  return (
    <section aria-label={t('widget.title')} className="flex h-full flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <header className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[15px] font-bold text-fg">
          <TrendingUp aria-hidden className="size-4 text-muted" />
          {t('widget.title')}
        </h2>
        {summary.data && summary.data.pending > 0 && (
          <span className="num rounded-full bg-accent-soft px-2 py-0.5 text-xs font-bold text-accent-ink">
            {t('widget.pending', { count: summary.data.pending })}
          </span>
        )}
      </header>

      {summary.isPending || upcoming.isPending ? (
        <div className="grid gap-2">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : summary.data?.enabled === false ? (
        <p className="text-sm text-muted">{t('widget.disabled')}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t('widget.none')}</p>
      ) : (
        <ul className="grid gap-1.5">
          {items.map((rec) => {
            const name = pick(rec.room_type.name, lang)
            const date = shortDate(rec.date, lang)
            return (
              <li key={rec.id} className="flex items-center gap-2.5 rounded-md border border-border px-2.5 py-2">
                <span className={cn('num w-14 shrink-0 rounded px-1 py-0.5 text-center text-xs font-bold', STEP_CLASS[stepOf(rec.change_percent)])}>
                  {signedPercent(rec.change_percent, lang)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-fg">
                    {name} · <span className="first-letter:uppercase">{date}</span>
                  </span>
                  <span className="num block text-xs text-muted">
                    {formatMoney(rec.current_price, currency)} → {formatMoney(rec.recommended_price, currency)}
                  </span>
                </span>
                {canManage && rec.id && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t('widget.approveOne', { roomType: name, date })}
                    disabled={decision.isPending}
                    onClick={() => approve([rec.id as string])}
                  >
                    <Check aria-hidden />
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        <Link to="/app/revenue" className="flex items-center gap-1 text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('widget.viewAll')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
        {canManage && items.length > 0 && (
          <Button
            size="sm"
            loading={decision.isPending}
            onClick={() => approve(items.flatMap((rec) => (rec.id ? [rec.id] : [])))}
          >
            <Check aria-hidden />
            {t('widget.approveAll', { count: items.length })}
          </Button>
        )}
      </footer>
    </section>
  )
}
