import { ArrowRight, ChartColumn } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { KpiTile } from '@/components/KpiTile'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, formatPercent, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useReport, useReportCatalog, type ReportDef } from '../api'
import { RangeRuler } from '../components/RangeRuler'
import { CATEGORY_ICON, CATEGORY_ORDER, reportIcon, sortReports } from '../lib/catalog'
import { compactMoney } from '../lib/format'
import { presetRange } from '../lib/presets'
import { KPI_TILE_CLASS } from '../lib/styles'
import '../viz.css'

/** `/app/reports`: this month's performance at a glance, then every report the role can open, by category. */
export default function ReportsHubPage() {
  const { t } = useTranslation('reports')
  const { property } = useActiveProperty()
  const catalog = useReportCatalog()
  const businessDate = property?.business_date ?? ''
  const allowed = (catalog.data ?? []).filter((report) => report.allowed)
  const canPerformance = allowed.some((report) => report.id === 'performance')

  return (
    <div className="report-viz mx-auto flex w-full max-w-7xl flex-col gap-8">
      <PageHeader
        title={t('hub.title')}
        description={t('hub.description')}
        className="pb-0"
      />

      {canPerformance && businessDate && <MonthGlance businessDate={businessDate} currency={property?.currency ?? 'COP'} />}

      {catalog.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : catalog.isError ? (
        <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} />
      ) : allowed.length === 0 ? (
        <EmptyState icon={ChartColumn} title={t('hub.empty')} description={t('hub.emptyHint')} />
      ) : (
        CATEGORY_ORDER.map((category) => {
          const reports = sortReports(allowed.filter((report) => report.category === category))
          if (reports.length === 0) return null
          return <CategorySection key={category} category={category} reports={reports} />
        })
      )}
    </div>
  )
}

function CategorySection({ category, reports }: { category: ReportDef['category']; reports: ReportDef[] }) {
  const { t } = useTranslation('reports')
  const Icon = CATEGORY_ICON[category]
  const headingId = `reports-category-${category}`
  return (
    <section aria-labelledby={headingId} className="grid gap-3">
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 border-b border-border pb-2">
        <div className="flex items-center gap-2.5">
          <Icon aria-hidden className="size-[18px] text-accent-ink" />
          <h2 id={headingId} className="text-[17px] font-bold tracking-[-0.01em] text-fg">
            {t(`categories.${category}.title`)}
          </h2>
          <span className="num text-xs font-semibold text-subtle">{t('hub.count', { count: reports.length })}</span>
        </div>
        <p className="text-[13px] text-muted">{t(`categories.${category}.description`)}</p>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {reports.map((report) => {
          const ReportIcon = reportIcon(report.id)
          return (
            <li key={report.id}>
              <Link
                to={`/app/reports/${report.id}`}
                className={cn(
                  'group flex h-full items-start gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs transition-[border-color,box-shadow]',
                  'hover:border-border-strong hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                )}
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted transition-colors group-hover:bg-accent-soft group-hover:text-accent-ink">
                  <ReportIcon aria-hidden className="size-[18px]" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[14px] font-bold text-fg">
                    {t(`reports.${report.id}.title`, { defaultValue: report.id })}
                    <ArrowRight
                      aria-hidden
                      className="size-3.5 -translate-x-1 text-accent-ink opacity-0 transition-[opacity,translate] group-hover:translate-x-0 group-hover:opacity-100"
                    />
                  </span>
                  <span className="mt-0.5 block text-[13px] leading-5 text-muted">
                    {t(`reports.${report.id}.description`, { defaultValue: '' })}
                  </span>
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** This month in four numbers, with the counted days of the month below (the same engine as every report). */
function MonthGlance({ businessDate, currency }: { businessDate: string; currency: string }) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const range = presetRange('thisMonth', businessDate)
  const report = useReport('performance', { start: range.start, end: range.end, lang })
  const kpis = new Map((report.data?.summary ?? []).map((kpi) => [kpi.key, kpi]))
  const value = (key: string) => kpis.get(key)?.value ?? null

  return (
    <section aria-labelledby="reports-glance" className="grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="reports-glance" className="text-[15px] font-bold text-fg">
            {t('hub.glance')}
          </h2>
          <p className="text-xs text-muted">
            {t('hub.glanceHint', { start: formatDate(range.start, undefined, lang), end: formatDate(range.end, undefined, lang) })}
          </p>
        </div>
        <Link
          to="/app/reports/performance?preset=thisMonth"
          className="flex items-center gap-1 text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline"
        >
          {t('hub.openPerformance')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </header>
      {report.isPending ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-[104px] rounded-lg" />
          ))}
        </div>
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => void report.refetch()} className="py-6" />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiTile className={KPI_TILE_CLASS} label={kpis.get('occupancy')?.label ?? ''} value={formatPercent(Number(value('occupancy') ?? 0), 1, lang)} />
          <KpiTile className={KPI_TILE_CLASS} label={kpis.get('adr')?.label ?? ''} value={compactMoney(value('adr'), currency, lang, 10_000_000)} />
          <KpiTile className={KPI_TILE_CLASS} label={kpis.get('revpar')?.label ?? ''} value={compactMoney(value('revpar'), currency, lang, 10_000_000)} />
          <KpiTile
            className={KPI_TILE_CLASS}
            label={kpis.get('room_revenue')?.label ?? ''}
            value={compactMoney(value('room_revenue'), currency, lang, 10_000_000)}
          />
        </div>
      )}
      <RangeRuler range={range} compare={null} businessDate={businessDate} forecast />
    </section>
  )
}
