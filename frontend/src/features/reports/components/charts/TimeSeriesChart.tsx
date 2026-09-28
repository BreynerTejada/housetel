import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
  type TooltipContentProps,
  type TooltipValueType,
} from 'recharts'
import { Badge } from '@/components/ui/badge'
import type { Lang } from '@/lib/format'
import type { ChartSpec } from '../../api'
import { chartValue, longDate, shortDate, tickValue } from '../../lib/format'
import { ChartTooltip, type TooltipRow } from './ChartTooltip'
import { barPath } from './shapes'

const SLOT = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)']
const Y_WIDTH = { money: 68, percent: 44, number: 40 } as const
const AXIS_TICK = { fontSize: 11, fill: 'var(--viz-tick)' }

type Row = Record<string, string | number | boolean | null>

/**
 * Time series of a report (one y-axis, never two): lines for rates (occupancy, ADR, RevPAR), columns for
 * amounts and counts, stacked columns for parts of a whole. Nights from the business date on are a forecast:
 * dashed line / softer column. The comparison period is a gray line; the business date is a thin rule.
 */
export function TimeSeriesChart({ chart, currency, lang, height }: { chart: ChartSpec; currency: string; lang: Lang; height: number }) {
  const { t } = useTranslation('reports')
  const primary = chart.series.filter((series) => series.role === 'primary')
  const compare = chart.series.filter((series) => series.role === 'compare')
  const stacks = chart.series.filter((series) => series.role === 'stack')
  const kind = chart.x_type === 'month' ? 'month' : 'date'
  const forecastFrom = chart.forecast_from
  const isBars = chart.type !== 'line'
  const sparse = chart.data.length < 3

  const data = useMemo<Row[]>(() => {
    const rows: Row[] = chart.data.map((row) => ({ ...row }))
    if (chart.type !== 'line' || !forecastFrom) return rows
    const first = rows.findIndex((row) => String(row[chart.x]) >= forecastFrom)
    for (const series of chart.series.filter((item) => item.role === 'primary')) {
      rows.forEach((row, index) => {
        const inForecast = first >= 0 && index >= first
        row[`${series.key}__actual`] = inForecast ? null : row[series.key]
        // The last actual night is repeated in the forecast line so the two halves join.
        row[`${series.key}__forecast`] = inForecast || (first > 0 && index === first - 1) ? row[series.key] : null
      })
    }
    return rows
  }, [chart, forecastFrom])

  const isForecast = (row: Row) => Boolean(forecastFrom && String(row[chart.x]) >= forecastFrom)
  const fmt = (value: unknown) => chartValue(value, chart.value_type, currency, lang)

  function renderTooltip({ active, payload }: TooltipContentProps<TooltipValueType, string | number>) {
    if (!active || !payload?.length) return null
    const row = payload[0]!.payload as Row
    const x = String(row[chart.x])
    const forecastRow = isForecast(row)
    const rows: TooltipRow[] = []
    if (chart.type === 'stacked_column') {
      stacks.forEach((series, index) => {
        rows.push({ key: series.key, label: series.label, value: fmt(row[series.key]), color: SLOT[index] ?? SLOT[0]!, mark: 'bar' })
      })
    } else {
      for (const series of primary) {
        const value = row[series.key]
        const negative = typeof value === 'number' && value < 0
        const color = negative ? 'var(--viz-2)' : forecastRow && isBars ? 'var(--viz-forecast)' : 'var(--viz-1)'
        rows.push({
          key: series.key,
          label: series.label,
          value: fmt(value),
          color,
          mark: isBars ? 'bar' : forecastRow ? 'dashed' : 'line',
        })
      }
    }
    for (const series of compare) {
      const date = typeof row.date_prev === 'string' ? longDate(row.date_prev, kind, lang) : undefined
      rows.push({ key: series.key, label: series.label, value: fmt(row[series.key]), color: 'var(--viz-compare)', mark: 'line', hint: date })
    }
    return (
      <ChartTooltip
        title={longDate(x, kind, lang)}
        badge={forecastRow ? <Badge tone="accent">{t('chart.forecast')}</Badge> : undefined}
        rows={rows}
      />
    )
  }

  const percentDomain: [number, (max: number) => number] = [0, (max) => Math.max(100, Math.ceil(max))]
  const dot = (color: string) => (sparse ? { r: 4, fill: color, stroke: 'var(--viz-surface)', strokeWidth: 2 } : false)
  const activeDot = (color: string) => ({ r: 4, fill: color, stroke: 'var(--viz-surface)', strokeWidth: 2 })

  function columnShape(props: BarShapeProps) {
    const value = Array.isArray(props.value) ? props.value[1] - props.value[0] : Number(props.value)
    return <path d={barPath(props.x, props.y, props.width, props.height, value < 0 ? 'bottom' : 'top')} fill={props.fill} />
  }

  function stackShape(index: number) {
    return function StackSegment(props: BarShapeProps) {
      const row = (props.payload ?? {}) as Row
      const present = (key: string) => Number(row[key] ?? 0) > 0
      const above = stacks.slice(index + 1).some((series) => present(series.key))
      const below = stacks.slice(0, index).some((series) => present(series.key))
      // A 2px surface gap separates touching segments; only the top segment gets the rounded end.
      const gap = below ? 2 : 0
      const height = Math.abs(props.height) - gap
      if (height <= 0.5) return <g />
      const top = Math.min(props.y, props.y + props.height)
      return <path d={barPath(props.x, top, props.width, height, above ? 'none' : 'top')} fill={props.fill} />
    }
  }

  return (
    <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 320, height }}>
      <ComposedChart data={data} margin={{ top: chart.marker ? 20 : 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="18%">
        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
        <XAxis
          dataKey={chart.x}
          tickFormatter={(value) => shortDate(String(value), kind, lang)}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={{ stroke: 'var(--viz-axis)' }}
          tickMargin={6}
          minTickGap={18}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(value) => tickValue(Number(value), chart.value_type, currency, lang)}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={Y_WIDTH[chart.value_type]}
          tickCount={5}
          allowDecimals={chart.value_type !== 'number'}
          domain={chart.value_type === 'percent' ? percentDomain : undefined}
        />
        <Tooltip
          content={renderTooltip}
          cursor={isBars ? { fill: 'var(--surface-2)', fillOpacity: 0.8 } : { stroke: 'var(--viz-axis)', strokeWidth: 1 }}
          isAnimationActive={false}
        />
        {chart.marker && (
          <ReferenceLine
            x={chart.marker.x}
            stroke="var(--text-muted)"
            strokeWidth={1}
            label={{ value: chart.marker.label, position: 'top', fill: 'var(--text-muted)', fontSize: 11, fontWeight: 600 }}
          />
        )}

        {chart.type === 'column' &&
          primary.map((series) => (
            <Bar key={series.key} dataKey={series.key} name={series.label} maxBarSize={24} isAnimationActive={false} shape={columnShape}>
              {data.map((row, index) => {
                const value = Number(row[series.key] ?? 0)
                const fill = value < 0 ? 'var(--viz-2)' : isForecast(row) ? 'var(--viz-forecast)' : 'var(--viz-1)'
                return <Cell key={index} fill={fill} />
              })}
            </Bar>
          ))}

        {chart.type === 'stacked_column' &&
          stacks.map((series, index) => (
            <Bar
              key={series.key}
              dataKey={series.key}
              name={series.label}
              stackId="stack"
              fill={SLOT[index] ?? SLOT[0]}
              maxBarSize={24}
              isAnimationActive={false}
              shape={stackShape(index)}
            />
          ))}

        {chart.type === 'line' &&
          primary.flatMap((series) =>
            forecastFrom
              ? [
                  <Line
                    key={`${series.key}-actual`}
                    dataKey={`${series.key}__actual`}
                    name={series.label}
                    stroke="var(--viz-1)"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    dot={dot('var(--viz-1)')}
                    activeDot={activeDot('var(--viz-1)')}
                    isAnimationActive={false}
                  />,
                  <Line
                    key={`${series.key}-forecast`}
                    dataKey={`${series.key}__forecast`}
                    name={`${series.label} · ${t('chart.forecast')}`}
                    stroke="var(--viz-1)"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                    strokeLinecap="round"
                    dot={dot('var(--viz-1)')}
                    activeDot={activeDot('var(--viz-1)')}
                    isAnimationActive={false}
                  />,
                ]
              : [
                  <Line
                    key={series.key}
                    dataKey={series.key}
                    name={series.label}
                    stroke="var(--viz-1)"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    dot={dot('var(--viz-1)')}
                    activeDot={activeDot('var(--viz-1)')}
                    isAnimationActive={false}
                  />,
                ],
          )}

        {compare.map((series) => (
          <Line
            key={series.key}
            dataKey={series.key}
            name={series.label}
            stroke="var(--viz-compare)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={dot('var(--viz-compare)')}
            activeDot={activeDot('var(--viz-compare)')}
            isAnimationActive={false}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

