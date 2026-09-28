import { ArrowRight, ChartNoAxesColumn } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, type BarShapeProps, type TooltipContentProps, type TooltipValueType } from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, formatPercent, normalizeLang } from '@/lib/format'
import { useReport } from '../api'
import { longDate } from '../lib/format'
import { presetRange } from '../lib/presets'
import { ChartTooltip } from './charts/ChartTooltip'
import { barPath } from './charts/shapes'
import '../viz.css'

type Row = Record<string, string | number | boolean | null>

/**
 * Today panel: occupancy of the next 14 nights (the occupancy-outlook report, same engine as every report).
 * Only the busiest night is labelled; the others are one hover (or the report) away.
 */
export default function OccupancyWidget() {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const businessDate = property?.business_date ?? ''
  const range = businessDate ? presetRange('next14', businessDate) : null
  const report = useReport('occupancy-outlook', { start: range?.start, end: range?.end, lang }, Boolean(range))
  const chart = report.data?.charts[0]
  const kpis = new Map((report.data?.summary ?? []).map((kpi) => [kpi.key, kpi]))
  const peakDate = typeof report.data?.meta.peak_date === 'string' ? report.data.meta.peak_date : null
  const average = kpis.get('occupancy')?.value
  const peak = kpis.get('peak')?.value
  const data: Row[] = chart?.data ?? []
  const available = report.data?.tables[0]?.totals?.available

  function renderTooltip({ active, payload }: TooltipContentProps<TooltipValueType, string | number>) {
    if (!active || !payload?.length) return null
    const row = payload[0]!.payload as Row
    return (
      <ChartTooltip
        title={longDate(String(row.date), 'date', lang)}
        rows={[{ key: 'occupancy', label: chart?.series[0]?.label ?? '', value: formatPercent(Number(row.occupancy ?? 0), 1, lang), color: 'var(--viz-1)', mark: 'bar' }]}
      />
    )
  }

  return (
    <section aria-label={t('widget.title')} className="report-viz flex h-full flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[15px] font-bold text-fg">
          <ChartNoAxesColumn aria-hidden className="size-4 text-muted" />
          {t('widget.title')}
        </h2>
        {average !== undefined && average !== null && (
          <span className="num rounded-full bg-accent-soft px-2 py-0.5 text-xs font-bold text-accent-ink">
            {t('widget.average', { value: formatPercent(Number(average), 1, lang) })}
          </span>
        )}
      </header>

      {report.isPending ? (
        <Skeleton className="h-32" />
      ) : !chart || Number(available ?? 0) === 0 ? (
        <p className="py-8 text-center text-sm text-muted">{t('widget.empty')}</p>
      ) : (
        <>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 300, height: 128 }}>
              <BarChart data={data} margin={{ top: 18, right: 2, bottom: 0, left: 2 }} barCategoryGap="16%">
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) => formatDate(String(value), 'EEEEE', lang).toUpperCase()}
                  tick={{ fontSize: 10, fill: 'var(--viz-tick)' }}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--viz-axis)' }}
                  interval={0}
                  tickMargin={4}
                />
                <Tooltip content={renderTooltip} cursor={{ fill: 'var(--surface-2)', fillOpacity: 0.8 }} isAnimationActive={false} />
                <Bar
                  dataKey="occupancy"
                  maxBarSize={20}
                  isAnimationActive={false}
                  shape={(props: BarShapeProps) => <path d={barPath(props.x, props.y, props.width, props.height, 'top')} fill={props.fill} />}
                  label={({ x, y, width, index }: { x?: number | string; y?: number | string; width?: number | string; index?: number }) =>
                    index !== undefined && data[index]?.date === peakDate ? (
                      <text
                        x={Number(x) + Number(width) / 2}
                        y={Number(y) - 5}
                        textAnchor="middle"
                        fontSize={11}
                        fontWeight={700}
                        fill="var(--text)"
                        style={{ fontVariantNumeric: 'tabular-nums' }}
                      >
                        {formatPercent(Number(data[index]?.occupancy ?? 0), 0, lang)}
                      </text>
                    ) : null
                  }
                >
                  {data.map((row, index) => (
                    <Cell key={index} fill={row.date === peakDate ? 'var(--viz-1)' : 'var(--viz-forecast)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {peakDate && peak !== undefined && peak !== null && (
            <p className="text-xs text-muted">
              {t('widget.peak', {
                date: formatDate(peakDate, lang === 'en' ? 'EEE, MMM d' : 'EEE d MMM', lang),
                value: formatPercent(Number(peak), 1, lang),
              })}
            </p>
          )}
        </>
      )}

      <footer className="mt-auto pt-1">
        <Link
          to="/app/reports/occupancy-outlook?preset=next14"
          className="flex items-center gap-1 text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline"
        >
          {t('widget.open')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </footer>
    </section>
  )
}
