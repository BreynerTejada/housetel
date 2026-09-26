import { ArrowDownRight, ArrowUpRight, Minus, type LucideIcon } from 'lucide-react'
import { useId, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface TrendPoint {
  label: string
  value: number
}

export interface KpiTileProps {
  /** Sentence case, no trailing colon. */
  label: string
  /** Already formatted (auto-compact big numbers: "$ 4,2 M"). */
  value: ReactNode
  /** Signed change vs `deltaPeriod`. */
  delta?: number | null
  /** Absolute, formatted change ("4,2 pp"); defaults to |delta| with one decimal. */
  deltaLabel?: string
  /** Named comparison period ("vs. semana pasada"). */
  deltaPeriod?: string
  /** Whether a rise is good news (occupancy) or bad news (cancellations). */
  intent?: 'higher-is-better' | 'lower-is-better' | 'neutral'
  /** Up to ~12 points; the latest one is highlighted. */
  trend?: TrendPoint[]
  formatTrendValue?: (value: number) => string
  icon?: LucideIcon
  className?: string
}

const TONE = { good: 'text-success-ink', bad: 'text-danger-ink', neutral: 'text-muted' } as const

/** Stat tile (dataviz figure contract): label · value · signed delta · optional sparkline. */
export function KpiTile({
  label,
  value,
  delta,
  deltaLabel,
  deltaPeriod,
  intent = 'higher-is-better',
  trend,
  formatTrendValue,
  icon: Icon,
  className,
}: KpiTileProps) {
  const { t, i18n } = useTranslation()
  const hasDelta = delta !== undefined && delta !== null && Number.isFinite(delta)
  const direction = !hasDelta || delta === 0 ? 'flat' : delta > 0 ? 'up' : 'down'
  const good = intent === 'higher-is-better' ? direction === 'up' : direction === 'down'
  const outcome = direction === 'flat' || intent === 'neutral' ? 'neutral' : good ? 'good' : 'bad'
  const amount = deltaLabel ?? (hasDelta ? formatNumber(Math.abs(delta), normalizeLang(i18n.language), 1) : '')
  const Arrow = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus

  return (
    <div className={cn('flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs', className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold text-muted">{label}</p>
        {Icon && <Icon aria-hidden className="size-4 text-subtle" />}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[28px] leading-8 font-semibold tracking-[-0.02em] text-fg">{value}</p>
          {hasDelta && (
            <p
              data-intent={outcome}
              data-direction={direction}
              className={cn('mt-1.5 flex flex-wrap items-center gap-x-1 text-xs font-semibold', TONE[outcome])}
            >
              <Arrow aria-hidden className="size-3.5" />
              {direction === 'flat' ? (
                <span>{t('kpi.flat')}</span>
              ) : (
                <>
                  <span aria-hidden className="num">
                    {amount}
                  </span>
                  <span className="sr-only">{t(direction === 'up' ? 'kpi.up' : 'kpi.down', { value: amount })}</span>
                </>
              )}
              {deltaPeriod && <span className="ml-1 font-medium text-muted">{deltaPeriod}</span>}
            </p>
          )}
        </div>
        {trend && trend.length > 1 && <Sparkline label={label} points={trend} format={formatTrendValue} />}
      </div>
    </div>
  )
}

const W = 104
const H = 36
const PAD = 4

function Sparkline({ label, points, format = String }: { label: string; points: TrendPoint[]; format?: (v: number) => string }) {
  const { t } = useTranslation()
  const captionId = useId()
  const [active, setActive] = useState<number | null>(null)
  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const x = (i: number) => PAD + (i * (W - PAD * 2)) / (points.length - 1)
  const y = (v: number) => H - PAD - ((v - min) / (max - min || 1)) * (H - PAD * 2)
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const last = points.length - 1
  const shown = active ?? last
  const first = points[0]!
  const current = points[shown]!

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.width) return
    const ratio = (event.clientX - rect.left) / rect.width
    setActive(Math.min(last, Math.max(0, Math.round(ratio * last))))
  }

  function onKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    const moves: Record<string, number> = { ArrowLeft: shown - 1, ArrowRight: shown + 1, Home: 0, End: last }
    if (!(event.key in moves)) return
    event.preventDefault()
    setActive(Math.min(last, Math.max(0, moves[event.key]!)))
  }

  return (
    <div className="relative shrink-0">
      {active !== null && (
        <p
          role="status"
          className="num pointer-events-none absolute right-0 bottom-full mb-1 rounded-md bg-fg px-2 py-1 text-[11px] font-semibold whitespace-nowrap text-bg shadow-md"
        >
          {current.label} · {format(current.value)}
        </p>
      )}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        role="img"
        tabIndex={0}
        aria-label={`${label}: ${first.label} – ${points[last]!.label}`}
        aria-describedby={captionId}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive(last)}
        onBlur={() => setActive(null)}
        onKeyDown={onKeyDown}
        className="overflow-visible rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
      >
        <path d={path} fill="none" className="stroke-subtle" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {active !== null && active !== last && (
          <line x1={x(active)} x2={x(active)} y1={0} y2={H} className="stroke-border-strong" strokeWidth={1} />
        )}
        <circle cx={x(shown)} cy={y(current.value)} r={3.5} className="fill-accent stroke-surface" strokeWidth={2} />
      </svg>
      <table id={captionId} className="sr-only">
        <caption>{label}</caption>
        <tbody>
          <tr>
            <th scope="col">{t('kpi.period')}</th>
            <th scope="col">{label}</th>
          </tr>
          {points.map((point) => (
            <tr key={point.label}>
              <th scope="row">{point.label}</th>
              <td>{format(point.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
