/**
 * Platform charts (super-admin). Dataviz contract: one axis, thin columns (≤ 24 px) with a 4 px rounded
 * data end and square baseline, a 2 px surface gap between stacked segments, hairline solid grid, text in text
 * tokens, a legend for ≥ 2 series, a tooltip on every column and a table twin.
 *
 * Palette (validated with the dataviz validator, both modes PASS): slot 1 = subscriptions (terracotta, the
 * product accent), slot 2 = marketplace (blue). Light #b4583b / #3a6ea8 on #ffffff; dark #d4775c / #5b8fc7
 * on #1c1a18. Defined here as feature-scoped CSS variables (the shared tokens have no chart colors).
 */
import { Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type BarShapeProps, type TooltipContentProps } from 'recharts'
import { Button } from '@/components/ui/button'
import { formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { compactMoney, monthLabel } from '../helpers'

export const CHART_VARS =
  '[--chart-1:#b4583b] [--chart-2:#3a6ea8] dark:[--chart-1:#d4775c] dark:[--chart-2:#5b8fc7]'

const RADIUS = 4
const GAP = 2
const AXIS_TICK = { fill: 'var(--text-muted)', fontSize: 11 }

function roundedTopPath(x: number, y: number, width: number, height: number): string {
  if (width <= 0 || height <= 0) return ''
  const r = Math.min(RADIUS, width / 2, height)
  return [
    `M${x},${y + height}`,
    `L${x},${y + r}`,
    `A${r},${r} 0 0 1 ${x + r},${y}`,
    `L${x + width - r},${y}`,
    `A${r},${r} 0 0 1 ${x + width},${y + r}`,
    `L${x + width},${y + height}`,
    'Z',
  ].join(' ')
}

/** Column segment: rounded when it is the top of its stack, otherwise square with a 2 px gap above. */
function segmentShape(isTop: (row: Record<string, unknown>) => boolean) {
  return function Segment(props: BarShapeProps) {
    const { x, y, width, height, fill, payload } = props
    if (!height || height <= 0) return <g />
    if (isTop(payload as Record<string, unknown>)) return <path d={roundedTopPath(x, y, width, height)} fill={fill} />
    const gap = height > GAP ? GAP : 0
    return <rect x={x} y={y + gap} width={width} height={height - gap} fill={fill} />
  }
}

export interface SeriesDef {
  key: string
  label: string
  color: string
}

interface MonthRow {
  month: string
  [key: string]: string | number
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  lang,
  footer,
}: Partial<TooltipContentProps<number, string>> & {
  series: SeriesDef[]
  lang: string
  footer?: (row: MonthRow) => ReactNode
}) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload as MonthRow | undefined
  if (!row) return null
  const total = series.reduce((sum, s) => sum + Number(row[s.key] ?? 0), 0)
  return (
    <div className="min-w-44 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm shadow-md">
      <p className="mb-1.5 text-xs font-semibold text-muted first-letter:uppercase">{monthLabel(String(label ?? row.month), lang, 'long')}</p>
      <ul className="grid grid-cols-1 gap-1">
        {[...series].reverse().map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span aria-hidden className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
            <span className="num font-semibold text-fg">{formatMoney(row[s.key] as number)}</span>
            <span className="text-xs text-muted">{s.label}</span>
          </li>
        ))}
      </ul>
      {series.length > 1 && (
        <p className="mt-1.5 flex items-baseline justify-between gap-3 border-t border-border pt-1.5 text-xs text-muted">
          <span>Σ</span>
          <span className="num font-semibold text-fg">{formatMoney(total)}</span>
        </p>
      )}
      {footer?.(row)}
    </div>
  )
}

/**
 * Monthly columns: one series (no legend, the title names it) or a stack of series (legend above).
 * `rows[].month` = "YYYY-MM"; values are numbers.
 */
export function MonthlyColumns({
  title,
  description,
  rows,
  series,
  tooltipFooter,
  tableExtra,
  height = 240,
}: {
  title: string
  description?: string
  rows: MonthRow[]
  series: SeriesDef[]
  tooltipFooter?: (row: MonthRow) => ReactNode
  tableExtra?: { label: string; value: (row: MonthRow) => ReactNode }
  height?: number
}) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const [asTable, setAsTable] = useState(false)
  const stacked = series.length > 1

  return (
    <section className={cn('grid grid-cols-1 gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5', CHART_VARS)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-bold text-fg">{title}</h2>
          {description && <p className="text-sm text-muted">{description}</p>}
        </div>
        <Button variant="ghost" size="sm" aria-pressed={asTable} onClick={() => setAsTable((value) => !value)}>
          <Table2 aria-hidden />
          {asTable ? t('charts.showChart') : t('charts.showTable')}
        </Button>
      </div>
      {stacked && !asTable && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label={t('charts.legend')}>
          {series.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th scope="col" className="py-2 pr-3 font-semibold">{t('charts.month')}</th>
                {series.map((s) => (
                  <th key={s.key} scope="col" className="py-2 pr-3 text-right font-semibold">{s.label}</th>
                ))}
                {tableExtra && <th scope="col" className="py-2 text-right font-semibold">{tableExtra.label}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.month} className="border-b border-border last:border-0">
                  <th scope="row" className="py-1.5 pr-3 text-left font-medium text-fg first-letter:uppercase">
                    {monthLabel(row.month, lang, 'long')}
                  </th>
                  {series.map((s) => (
                    <td key={s.key} className="num py-1.5 pr-3 text-right text-fg">{formatMoney(row[s.key] as number)}</td>
                  ))}
                  {tableExtra && <td className="num py-1.5 text-right text-fg">{tableExtra.value(row)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }} className="-ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="28%">
              <CartesianGrid vertical={false} stroke="var(--border)" strokeWidth={1} />
              <XAxis
                dataKey="month"
                tickFormatter={(value: string) => monthLabel(value, lang)}
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={{ stroke: 'var(--border)' }}
                interval="preserveStartEnd"
                minTickGap={8}
              />
              <YAxis
                tickFormatter={(value: number) => compactMoney(value, lang)}
                tick={{ ...AXIS_TICK, className: 'num' }}
                tickLine={false}
                axisLine={false}
                width={64}
              />
              <Tooltip
                cursor={{ fill: 'var(--surface-2)' }}
                content={(props) => (
                  <ChartTooltip {...(props as TooltipContentProps<number, string>)} series={series} lang={lang} footer={tooltipFooter} />
                )}
              />
              {series.map((s, index) => {
                const above = series.slice(index + 1)
                return (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    name={s.label}
                    stackId={stacked ? 'total' : undefined}
                    fill={s.color}
                    maxBarSize={24}
                    isAnimationActive={false}
                    shape={segmentShape((row) => above.every((other) => !Number(row[other.key] ?? 0)))}
                  />
                )
              })}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

export interface Segment {
  key: string
  label: string
  value: number
  /** Tailwind background class (status tokens). */
  className: string
  icon: ReactNode
}

/** Part-to-whole strip (e.g. organizations by status): 2 px surface gaps, legend with icon + label + count. */
export function SegmentStrip({ title, segments, total }: { title: string; segments: Segment[]; total: number }) {
  const visible = segments.filter((segment) => segment.value > 0)
  return (
    <div className="grid grid-cols-1 gap-3">
      <div aria-hidden className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full bg-surface-2">
        {visible.map((segment) => (
          <span key={segment.key} className={cn('h-full first:rounded-l-full last:rounded-r-full', segment.className)} style={{ flexGrow: segment.value }} />
        ))}
      </div>
      <ul className="grid grid-cols-1 gap-1.5 text-sm" aria-label={title}>
        {segments.map((segment) => (
          <li key={segment.key} className="flex items-center justify-between gap-3">
            <span className="inline-flex min-w-0 items-center gap-2 text-muted">
              {segment.icon}
              <span className="truncate">{segment.label}</span>
            </span>
            <span className="num whitespace-nowrap font-semibold text-fg">
              {segment.value}
              {total > 0 && (
                <span className="ml-1.5 inline-block w-10 text-right text-xs font-normal text-muted">
                  {Math.round((segment.value * 100) / total)} %
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
