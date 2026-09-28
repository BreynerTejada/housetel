import { ChartColumn, Table2 } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useMediaQuery } from '@/lib/hooks'
import { normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ChartSpec } from '../api'
import { chartValue, countryName, longDate } from '../lib/format'
import { BarList } from './charts/BarList'
import { CategoryColumns } from './charts/CategoryColumns'
import { SeriesKey } from './charts/ChartTooltip'
import { StatusStrip } from './charts/StatusStrip'
import { TimeSeriesChart } from './charts/TimeSeriesChart'

const SLOT = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)']

/**
 * The charts of a report in one card. Several charts (performance: occupancy, ADR, RevPAR, revenue) share the
 * card as tabs, one at a time — never two y-scales on one plot. Every chart has a table view with the same
 * numbers (the accessible twin), and a legend whenever it shows two or more series.
 */
export function ChartCard({
  charts,
  currency,
  selected,
  onSelect,
  loading,
}: {
  charts: ChartSpec[]
  currency: string
  selected: string | null
  onSelect: (key: string) => void
  loading: boolean
}) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const phone = !useMediaQuery('(min-width: 640px)')
  const titleId = useId()
  if (charts.length === 0) return null
  const chart = charts.find((item) => item.key === selected) ?? charts[0]!
  const empty = chart.data.length === 0 || chart.data.every((row) => chart.series.every((series) => !Number(row[series.key] ?? 0)))

  return (
    <section aria-labelledby={titleId} className="rounded-lg border border-border bg-surface shadow-xs">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border px-4">
        {charts.length > 1 ? (
          <Tabs value={chart.key} onValueChange={onSelect} className="min-w-0 flex-1">
            <TabsList aria-label={t('chart.metric')} className="border-b-0">
              {charts.map((item) => (
                <TabsTrigger key={item.key} value={item.key} className="h-12">
                  {item.title}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : (
          <h2 className="py-3.5 text-[15px] font-bold text-fg">{chart.title}</h2>
        )}
        <ToggleGroup
          type="single"
          value={view}
          onValueChange={(value) => value && setView(value as 'chart' | 'table')}
          aria-label={t('chart.view')}
          className="my-2"
        >
          <ToggleGroupItem value="chart" aria-label={t('chart.chart')}>
            <ChartColumn aria-hidden />
            <span className="hidden sm:inline">{t('chart.chart')}</span>
          </ToggleGroupItem>
          <ToggleGroupItem value="table" aria-label={t('chart.table')}>
            <Table2 aria-hidden />
            <span className="hidden sm:inline">{t('chart.table')}</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </header>

      <figure className={cn('m-0 grid gap-3 p-4 transition-opacity', loading && 'opacity-60')} aria-busy={loading || undefined}>
        <figcaption id={titleId} className="sr-only">
          {chart.title}
        </figcaption>
        {empty ? (
          <p className="py-16 text-center text-sm text-muted">{t('chart.empty')}</p>
        ) : view === 'table' ? (
          <ChartDataTable chart={chart} currency={currency} lang={lang} />
        ) : (
          <>
            <Legend chart={chart} />
            <ChartBody chart={chart} currency={currency} lang={lang} height={phone ? 220 : 280} unknownLabel={t('table.unknown')} />
          </>
        )}
      </figure>
    </section>
  )
}

function ChartBody({ chart, currency, lang, height, unknownLabel }: { chart: ChartSpec; currency: string; lang: Lang; height: number; unknownLabel: string }) {
  if (chart.type === 'hbar') return <BarList chart={chart} currency={currency} lang={lang} unknownLabel={unknownLabel} />
  if (chart.type === 'status_bar') return <StatusStrip chart={chart} lang={lang} />
  if (chart.x_type === 'text') return <CategoryColumns chart={chart} currency={currency} lang={lang} height={height} />
  return <TimeSeriesChart chart={chart} currency={currency} lang={lang} height={height} />
}

/** Series keys (always for 2+ series) plus the keys a reader needs to decode forecast, polarity and today. */
function Legend({ chart }: { chart: ChartSpec }) {
  const { t } = useTranslation('reports')
  if (chart.type === 'hbar' || chart.type === 'status_bar' || chart.x_type === 'text') return null
  const stacks = chart.series.filter((series) => series.role === 'stack')
  const primary = chart.series.filter((series) => series.role === 'primary')
  const compare = chart.series.filter((series) => series.role === 'compare')
  const bars = chart.type !== 'line'
  const negatives = chart.type === 'column' && chart.data.some((row) => primary.some((series) => Number(row[series.key] ?? 0) < 0))
  const items: { key: string; label: string; color: string; mark: 'line' | 'bar' | 'dashed' }[] = []

  stacks.forEach((series, index) => items.push({ key: series.key, label: series.label, color: SLOT[index] ?? SLOT[0]!, mark: 'bar' }))
  if (primary.length > 0 && (compare.length > 0 || chart.forecast_from || negatives)) {
    for (const series of primary) {
      items.push({
        key: series.key,
        label: negatives ? t('chart.gain') : chart.forecast_from ? `${series.label} · ${t('chart.actual')}` : series.label,
        color: 'var(--viz-1)',
        mark: bars ? 'bar' : 'line',
      })
      if (chart.forecast_from) {
        items.push({
          key: `${series.key}-forecast`,
          label: `${series.label} · ${t('chart.forecast')}`,
          color: bars ? 'var(--viz-forecast)' : 'var(--viz-1)',
          mark: bars ? 'bar' : 'dashed',
        })
      }
      if (negatives) items.push({ key: `${series.key}-loss`, label: t('chart.loss'), color: 'var(--viz-2)', mark: 'bar' })
    }
  }
  for (const series of compare) items.push({ key: series.key, label: series.label, color: 'var(--viz-compare)', mark: 'line' })
  if (items.length === 0) return null

  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
      {items.map((item) => (
        <li key={item.key} className="inline-flex items-center gap-1.5">
          <SeriesKey color={item.color} mark={item.mark} />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

/** The chart's numbers as a table (same values, reachable without hovering). */
function ChartDataTable({ chart, currency, lang }: { chart: ChartSpec; currency: string; lang: Lang }) {
  const { t } = useTranslation('reports')
  const kind = chart.x_type === 'month' ? 'month' : 'date'
  const xLabel = (row: ChartSpec['data'][number]) => {
    const value = row[chart.x]
    if (chart.x_type === 'text') {
      if (typeof row.country === 'string' && row.country !== '__other__' && chart.x === 'label') return countryName(row.country, lang, String(value ?? ''))
      return String(value ?? t('table.unknown'))
    }
    return longDate(String(value), kind, lang)
  }
  const forecastFrom = chart.forecast_from

  return (
    <div className="max-h-[22rem] overflow-y-auto rounded-md border border-border">
      <Table>
        <caption className="sr-only">{chart.title}</caption>
        <TableHeader className="sticky top-0 bg-surface">
          <TableRow className="hover:bg-transparent">
            <TableHead scope="col">{chart.x_type === 'text' ? chart.title : t('chart.date')}</TableHead>
            {chart.series.map((series) => (
              <TableHead key={series.key} scope="col" className="text-right">
                {series.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {chart.data.map((row, index) => {
            const forecast = forecastFrom && chart.x_type !== 'text' ? String(row[chart.x]) >= forecastFrom : false
            return (
              <TableRow key={index}>
                <TableHead scope="row" className="h-auto py-2 font-medium text-fg first-letter:uppercase">
                  {xLabel(row)}
                  {forecast && <span className="ml-2 text-2xs font-semibold text-accent-ink">{t('chart.forecast')}</span>}
                </TableHead>
                {chart.series.map((series) => (
                  <TableCell key={series.key} className="num py-2 text-right">
                    {chartValue(row[series.key], chart.value_type, currency, lang)}
                  </TableCell>
                ))}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
