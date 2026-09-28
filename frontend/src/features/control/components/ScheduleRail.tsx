import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { dailyPattern, formatClock } from '../lib/cron'

const DAY = 1440
const NIGHT = [
  [0, 360],
  [1320, DAY],
] as const

/**
 * 24-hour rhythm rail: one day of the hotel (00–24, hotel time) with a tick at every run of the automation,
 * a band when it runs every few minutes, the night hours tinted and a marker at "now". It draws the real
 * schedule (the backend's cron), so "night audit at 02:00" or "every 15 minutes" reads at a glance.
 */
export function ScheduleRail({
  cron,
  everySeconds,
  label,
  nowMinutes,
  paused = false,
  className,
}: {
  cron: string | null
  everySeconds?: number | null
  /** Accessible description: automation name + readable schedule. */
  label: string
  nowMinutes: number | null
  paused?: boolean
  className?: string
}) {
  const { t } = useTranslation('control')
  const pattern = useMemo(() => dailyPattern(cron, everySeconds), [cron, everySeconds])
  const dense = (pattern?.times.length ?? 0) > 48
  const title = nowMinutes === null ? label : `${label} · ${t('automations.rail.now', { time: formatClock(nowMinutes) })}`

  return (
    <svg
      role="img"
      aria-label={title}
      viewBox={`0 0 ${DAY} 24`}
      preserveAspectRatio="none"
      className={cn('block h-6 w-full overflow-visible', paused ? 'text-subtle' : 'text-accent-ink', className)}
    >
      <title>{title}</title>
      {NIGHT.map(([from, to]) => (
        <rect key={from} x={from} y={3} width={to - from} height={16} fill="var(--surface-2)" />
      ))}
      <line x1={0} x2={DAY} y1={19} y2={19} stroke="var(--border-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      {[0, 360, 720, 1080, DAY].map((x) => (
        <line key={x} x1={x} x2={x} y1={16} y2={22} stroke="var(--border-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      ))}
      {pattern?.continuous && (
        <rect x={0} y={9} width={DAY} height={10} fill="currentColor" opacity={paused ? 0.25 : 0.32} rx={0} />
      )}
      {pattern?.times.map((minute) => (
        <line
          key={minute}
          x1={minute + 0.5}
          x2={minute + 0.5}
          y1={dense ? 10 : 5}
          y2={19}
          stroke="currentColor"
          strokeWidth={dense ? 1 : 2.5}
          strokeLinecap="round"
          opacity={dense ? 0.7 : 1}
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {nowMinutes !== null && (
        <g>
          <line
            x1={nowMinutes}
            x2={nowMinutes}
            y1={1}
            y2={23}
            stroke="var(--accent)"
            strokeWidth={1.5}
            strokeDasharray="2 2"
            vectorEffect="non-scaling-stroke"
          />
        </g>
      )}
    </svg>
  )
}

/** Hour legend aligned with ScheduleRail (00 · 06 · 12 · 18 · 24). */
export function RailLegend({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('num relative h-4 text-2xs text-subtle', className)}>
      {['00', '06', '12', '18', '24'].map((hour, index) => (
        <span
          key={hour}
          className="absolute top-0 -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
          style={{ left: `${index * 25}%` }}
        >
          {hour}
        </span>
      ))}
    </div>
  )
}
