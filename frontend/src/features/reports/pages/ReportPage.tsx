import { FileQuestion, LoaderCircle, Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { isApiError } from '@/lib/api'
import { useActiveProperty } from '@/lib/auth'
import { normalizeLang } from '@/lib/format'
import { useReport, useReportCatalog, type ReportDef } from '../api'
import { ChartCard } from '../components/ChartCard'
import { ExportMenu } from '../components/ExportMenu'
import { FilterBar } from '../components/FilterBar'
import { KpiRow } from '../components/KpiRow'
import { RangeRuler } from '../components/RangeRuler'
import { ReportNotes } from '../components/ReportNotes'
import { ReportTable } from '../components/ReportTable'
import { FORECAST_REPORTS } from '../lib/catalog'
import { useReportFilters } from '../lib/filters'
import '../viz.css'

/** `/app/reports/:reportId`: one report with its filters, KPI tiles, chart, tables and definitions. */
export default function ReportPage() {
  const { reportId = '' } = useParams()
  const { t } = useTranslation('reports')
  const catalog = useReportCatalog()
  const report = catalog.data?.find((item) => item.id === reportId)

  if (catalog.isPending) return <PageSkeleton />
  if (catalog.isError) return <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} />
  if (!report) {
    return (
      <EmptyState
        icon={FileQuestion}
        title={t('report.notFound')}
        description={t('report.notFoundHint')}
        action={
          <Button asChild variant="secondary">
            <Link to="/app/reports">{t('report.back')}</Link>
          </Button>
        }
      />
    )
  }
  if (!report.allowed) return <NoPermission permission={report.permission} />
  return <ReportView key={report.id} report={report} />
}

function ReportView({ report }: { report: ReportDef }) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const businessDate = property?.business_date ?? ''
  const filters = useReportFilters(report, businessDate, lang)
  const result = useReport(report.id, filters.query, Boolean(businessDate))
  const data = result.data
  const currency = data?.currency ?? property?.currency ?? 'COP'
  const refreshing = result.isFetching && !result.isPending
  const compareRange = data?.compare ? { start: data.compare.start, end: data.compare.end } : null
  const stem = [report.id, property?.slug ?? 'hotel', ...(filters.range ? [filters.range.start, filters.range.end] : [businessDate])].join('_')

  return (
    <div className="report-viz mx-auto flex w-full max-w-7xl flex-col gap-5">
      <PageHeader
        breadcrumbs={[{ label: t('report.back'), to: '/app/reports' }, { label: t(`categories.${report.category}.title`) }]}
        title={t(`reports.${report.id}.title`, { defaultValue: data?.title ?? report.id })}
        description={t(`reports.${report.id}.description`, { defaultValue: '' })}
        actions={<ExportMenu reportId={report.id} query={filters.query} fileStem={stem} />}
        className="pb-1"
      />

      <div className="grid gap-4 rounded-lg border border-border bg-surface px-4 py-3.5 shadow-xs">
        <FilterBar report={report} filters={filters} businessDate={businessDate} />
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0 flex-1">
            <RangeRuler range={filters.range} compare={compareRange} businessDate={businessDate} forecast={FORECAST_REPORTS.has(report.id)} />
          </div>
          <p role="status" aria-live="polite" className="flex h-5 shrink-0 items-center gap-1.5 text-xs text-muted">
            {refreshing && (
              <>
                <LoaderCircle aria-hidden className="size-3.5 animate-spin" />
                {t('report.updating')}
              </>
            )}
          </p>
        </div>
      </div>

      {result.isPending ? (
        <ContentSkeleton />
      ) : result.isError && !data ? (
        isApiError(result.error) && result.error.status === 403 ? (
          <NoPermission permission={report.permission} />
        ) : (
          <ErrorState error={result.error} onRetry={() => void result.refetch()} />
        )
      ) : data ? (
        <>
          {result.isError && <ErrorState error={result.error} onRetry={() => void result.refetch()} className="py-6" />}
          <KpiRow kpis={data.summary} currency={currency} compare={data.compare?.mode ?? null} />
          <ChartCard charts={data.charts} currency={currency} selected={filters.chart} onSelect={filters.setChart} loading={refreshing} />
          {data.tables.map((table) => (
            <ReportTable key={`${table.key}-${data.group_by ?? ''}`} table={table} currency={currency} loading={refreshing} />
          ))}
          <ReportNotes notes={data.notes} generatedAt={data.generated_at} />
        </>
      ) : null}
    </div>
  )
}

function NoPermission({ permission }: { permission: string }) {
  const { t } = useTranslation('reports')
  return (
    <EmptyState
      icon={Lock}
      title={t('report.noPermission')}
      description={t('report.noPermissionHint', { permission })}
      action={
        <Button asChild variant="secondary">
          <Link to="/app/reports">{t('report.back')}</Link>
        </Button>
      }
    />
  )
}

function PageSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
      <Skeleton className="h-16 w-72" />
      <Skeleton className="h-24 rounded-lg" />
      <ContentSkeleton />
    </div>
  )
}

function ContentSkeleton() {
  return (
    <div className="grid gap-5" aria-hidden>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-[104px] rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-lg" />
      <Skeleton className="h-64 rounded-lg" />
    </div>
  )
}
