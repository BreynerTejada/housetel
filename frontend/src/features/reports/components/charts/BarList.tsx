import type { Lang } from '@/lib/format'
import type { ChartSpec } from '../../api'
import { chartValue, countryName } from '../../lib/format'

const MAX_ROWS = 12

/**
 * Ranked horizontal bars (segments, countries, payment methods, balances) in plain HTML: long names wrap,
 * every bar carries its value at the tip and its share, so nothing hides behind a hover. One series → one
 * color; bars grow from a single baseline with a rounded data end.
 */
export function BarList({ chart, currency, lang, unknownLabel }: { chart: ChartSpec; currency: string; lang: Lang; unknownLabel: string }) {
  const series = chart.series[0]
  if (!series) return null
  const rows = chart.data
    .map((row) => ({
      label: labelOf(row, chart.x, lang, unknownLabel),
      value: Number(row[series.key] ?? 0),
    }))
    .filter((row) => Number.isFinite(row.value))
  const shown = rows.slice(0, MAX_ROWS)
  const max = Math.max(...shown.map((row) => Math.abs(row.value)), 0)
  const total = rows.reduce((sum, row) => sum + Math.max(row.value, 0), 0)

  return (
    <ul className="grid gap-2.5" aria-label={chart.title}>
      {shown.map((row, index) => {
        const width = max > 0 ? Math.max((Math.abs(row.value) / max) * 100, row.value ? 0.8 : 0) : 0
        const share = total > 0 && row.value > 0 ? Math.round((row.value / total) * 1000) / 10 : null
        return (
          <li
            key={`${row.label}-${index}`}
            className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(7rem,12rem)_minmax(0,1fr)_auto]"
          >
            <span className="truncate text-[13px] font-semibold text-fg" title={row.label}>
              {row.label}
            </span>
            <span className="col-span-2 row-start-2 flex h-3 items-center sm:col-span-1 sm:row-start-auto">
              <span
                className="h-3 rounded-r-[4px] bg-[var(--viz-1)] transition-opacity group-hover:opacity-85"
                style={{ width: `${width}%` }}
              />
            </span>
            <span className="num text-right text-[13px] whitespace-nowrap">
              <span className="font-bold text-fg">{chartValue(row.value, chart.value_type, currency, lang)}</span>
              {share !== null && (
                <span className="ml-1.5 text-xs text-muted">{chartValue(share, 'percent', currency, lang)}</span>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function labelOf(row: Record<string, unknown>, key: string, lang: Lang, unknownLabel: string): string {
  if (typeof row.country === 'string' && row.country && row.country !== '__other__' && key === 'label') {
    return countryName(row.country, lang, String(row.label ?? unknownLabel))
  }
  const value = row[key]
  return value === null || value === undefined || value === '' ? unknownLabel : String(value)
}
