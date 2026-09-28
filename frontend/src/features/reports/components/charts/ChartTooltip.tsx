import type { ReactNode } from 'react'

export interface TooltipRow {
  key: string
  label: string
  value: string
  /** CSS color of the series (a short line key; bars use a small block). */
  color: string
  mark: 'line' | 'bar' | 'dashed'
  /** Secondary text under the label (e.g. the comparison date). */
  hint?: string
}

/** One readout for every series at the hovered x: value first (strong), series name after. */
export function ChartTooltip({ title, badge, rows }: { title: string; badge?: ReactNode; rows: TooltipRow[] }) {
  if (rows.length === 0) return null
  return (
    <div className="min-w-44 rounded-lg border border-border bg-surface px-3 py-2.5 text-xs shadow-md">
      <p className="mb-1.5 flex items-center justify-between gap-3 font-semibold text-muted first-letter:uppercase">
        <span>{title}</span>
        {badge}
      </p>
      <ul className="grid gap-1.5">
        {rows.map((row) => (
          <li key={row.key} className="flex items-start gap-2">
            <SeriesKey color={row.color} mark={row.mark} className="mt-1.5" />
            <span className="min-w-0">
              <span className="num block text-[13px] leading-4 font-bold text-fg">{row.value}</span>
              <span className="block text-muted">{row.label}</span>
              {row.hint && <span className="block text-subtle">{row.hint}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Legend/tooltip key that mirrors the mark: a short stroke for lines, a small block for bars. */
export function SeriesKey({ color, mark, className }: { color: string; mark: 'line' | 'bar' | 'dashed'; className?: string }) {
  if (mark === 'bar') {
    return <span aria-hidden className={`inline-block size-2.5 shrink-0 rounded-[3px] ${className ?? ''}`} style={{ background: color }} />
  }
  return (
    <svg aria-hidden width="14" height="4" viewBox="0 0 14 4" className={`shrink-0 overflow-visible ${className ?? ''}`}>
      <line
        x1="1"
        y1="2"
        x2="13"
        y2="2"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={mark === 'dashed' ? '3 3' : undefined}
      />
    </svg>
  )
}
