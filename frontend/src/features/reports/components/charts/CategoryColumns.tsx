import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, type BarShapeProps, type TooltipContentProps, type TooltipValueType } from 'recharts'
import type { Lang } from '@/lib/format'
import type { ChartSpec } from '../../api'
import { chartValue } from '../../lib/format'
import { ChartTooltip } from './ChartTooltip'
import { barPath } from './shapes'

type Row = Record<string, string | number | boolean | null>

/**
 * Columns over ordered buckets (lead time, length of stay). One series → one color; every cap carries its
 * value, so the y-axis is left out.
 */
export function CategoryColumns({ chart, currency, lang, height }: { chart: ChartSpec; currency: string; lang: Lang; height: number }) {
  const series = chart.series[0]
  if (!series) return null
  const fmt = (value: unknown) => chartValue(value, chart.value_type, currency, lang)

  function renderTooltip({ active, payload }: TooltipContentProps<TooltipValueType, string | number>) {
    if (!active || !payload?.length || !series) return null
    const row = payload[0]!.payload as Row
    return (
      <ChartTooltip
        title={String(row[chart.x])}
        rows={[{ key: series.key, label: series.label, value: fmt(row[series.key]), color: 'var(--viz-1)', mark: 'bar' }]}
      />
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 320, height }}>
      <BarChart data={chart.data} margin={{ top: 22, right: 8, bottom: 0, left: 8 }} barCategoryGap="22%">
        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
        <XAxis
          dataKey={chart.x}
          tick={{ fontSize: 11, fill: 'var(--viz-tick)' }}
          tickLine={false}
          axisLine={{ stroke: 'var(--viz-axis)' }}
          interval={0}
          tickMargin={6}
          height={36}
        />
        <Tooltip content={renderTooltip} cursor={{ fill: 'var(--surface-2)', fillOpacity: 0.8 }} isAnimationActive={false} />
        <Bar
          dataKey={series.key}
          name={series.label}
          fill="var(--viz-1)"
          maxBarSize={24}
          isAnimationActive={false}
          shape={(props: BarShapeProps) => <path d={barPath(props.x, props.y, props.width, props.height, 'top')} fill={props.fill} />}
        >
          <LabelList
            dataKey={series.key}
            position="top"
            offset={6}
            formatter={(value) => fmt(value)}
            style={{ fontSize: 11, fontWeight: 600, fill: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
