import { formatNumber, formatPercent, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ChartSpec } from '../../api'

/** Room states keep the colors they have everywhere else in Housetel (tokens `--room-*`). */
const STATUS_COLOR: Record<string, string> = {
  clean: 'var(--room-clean)',
  inspected: 'var(--room-inspected)',
  dirty: 'var(--room-dirty)',
  out_of_service: 'var(--room-ooo)',
}

/**
 * Part-to-whole of room states: one stacked bar (2px surface gaps between segments) and a legend that names
 * every state with its count and share — the color never carries the meaning alone.
 */
export function StatusStrip({ chart, lang }: { chart: ChartSpec; lang: Lang }) {
  const series = chart.series[0]
  if (!series) return null
  const items = chart.data.map((row) => ({
    key: String(row.status ?? row[chart.x]),
    label: String(row.label ?? row[chart.x]),
    value: Number(row[series.key] ?? 0),
  }))
  const total = items.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="grid gap-4">
      <div className="flex h-4 w-full gap-[2px] overflow-hidden rounded-[4px]" role="img" aria-label={chart.title}>
        {items
          .filter((item) => item.value > 0)
          .map((item) => (
            <span
              key={item.key}
              className={cn('h-full first:rounded-l-[4px] last:rounded-r-[4px]', item.key === 'out_of_service' && 'hatch')}
              style={{ flexGrow: item.value, flexBasis: 0, backgroundColor: STATUS_COLOR[item.key] ?? 'var(--stone)' }}
              title={`${item.label}: ${item.value}`}
            />
          ))}
      </div>
      <ul className="flex flex-wrap gap-x-6 gap-y-2">
        {items.map((item) => (
          <li key={item.key} className="flex items-baseline gap-2">
            <span
              aria-hidden
              className={cn('size-2.5 shrink-0 translate-y-[1px] rounded-[3px]', item.key === 'out_of_service' && 'hatch')}
              style={{ backgroundColor: STATUS_COLOR[item.key] ?? 'var(--stone)' }}
            />
            <span className="text-[13px] text-muted">{item.label}</span>
            <span className="num text-[13px] font-bold text-fg">{formatNumber(item.value, lang, 0)}</span>
            <span className="num text-xs text-subtle">{total ? formatPercent((item.value / total) * 100, 0, lang) : '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
