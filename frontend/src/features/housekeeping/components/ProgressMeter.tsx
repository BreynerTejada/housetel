import { cn } from '@/lib/utils'

type Tone = 'success' | 'warning' | 'danger'

const FILL: Record<Tone, string> = { success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger' }
const TRACK: Record<Tone, string> = { success: 'bg-success-soft', warning: 'bg-warning-soft', danger: 'bg-danger-soft' }

/**
 * A single ratio against its limit (dataviz "meter"): the fill carries the state and the track is a lighter
 * step of the same ramp, so the state reads across the whole bar. The text around it names the values.
 */
export function ProgressMeter({
  value,
  max,
  label,
  tone = 'success',
  size = 'md',
  className,
}: {
  value: number
  max: number
  /** Accessible name ("Rooms ready today"). */
  label: string
  tone?: Tone
  size?: 'sm' | 'md'
  className?: string
}) {
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      className={cn('w-full overflow-hidden rounded-full', TRACK[tone], size === 'sm' ? 'h-1.5' : 'h-2.5', className)}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-500 ease-out', FILL[tone], ratio === 0 && 'hidden')}
        style={{ width: `${ratio * 100}%` }}
      />
    </div>
  )
}
