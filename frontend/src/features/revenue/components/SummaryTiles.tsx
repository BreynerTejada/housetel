import { CalendarClock, ChartNoAxesColumnIncreasing, Coins, Inbox, type LucideIcon } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { RevenueSummary } from '../api'
import { compactMoney, signedPercent } from '../lib/format'

/** Stat tile (dataviz figure contract): label · value · one supporting line. */
function StatTile({ label, value, detail, icon: Icon }: { label: string; value: ReactNode; detail?: ReactNode; icon: LucideIcon }) {
  const labelId = useId()
  return (
    <div role="group" aria-labelledby={labelId} className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <div className="flex items-center justify-between gap-2">
        <p id={labelId} className="text-[13px] font-semibold text-muted">
          {label}
        </p>
        <Icon aria-hidden className="size-4 text-subtle" />
      </div>
      <p className="truncate text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">{value}</p>
      {detail && <p className="text-xs font-medium text-muted">{detail}</p>}
    </div>
  )
}

/** KPIs of the pending recommendations (from the business date on). */
export function SummaryTiles({ summary, className }: { summary: RevenueSummary | undefined; className?: string }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  if (!summary) {
    return (
      <div className={cn('grid grid-cols-2 gap-3 lg:grid-cols-4', className)}>
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-[7.5rem] rounded-lg" />
        ))}
      </div>
    )
  }
  const upDown = `${t('kpis.up', { count: summary.up })} · ${t('kpis.down', { count: summary.down })}`
  return (
    <div className={cn('grid grid-cols-2 gap-3 lg:grid-cols-4', className)}>
      <StatTile label={t('kpis.pending')} value={summary.pending} detail={summary.pending ? upDown : t('kpis.nonePending')} icon={Inbox} />
      <StatTile
        label={t('kpis.avgChange')}
        value={summary.pending ? signedPercent(summary.avg_change_percent, lang) : '—'}
        detail={t('kpis.avgChangeHint')}
        icon={ChartNoAxesColumnIncreasing}
      />
      <StatTile
        label={t('kpis.impact')}
        value={summary.pending ? compactMoney(summary.estimated_impact, lang) : '—'}
        detail={
          summary.up && summary.down
            ? t('kpis.impactSplit', {
                up: `+${compactMoney(summary.impact_up, lang)}`,
                down: compactMoney(summary.impact_down, lang),
              })
            : t('kpis.impactHint')
        }
        icon={Coins}
      />
      <StatTile
        label={t('kpis.firstNight')}
        value={summary.first_date ? formatDate(summary.first_date, 'EEE d MMM', lang) : '—'}
        detail={t(summary.auto_apply ? 'kpis.autoApplyOn' : 'kpis.autoApplyOff')}
        icon={CalendarClock}
      />
    </div>
  )
}
