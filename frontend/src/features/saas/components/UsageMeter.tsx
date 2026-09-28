import { cn } from '@/lib/utils'

/**
 * Plan usage meter (dataviz meter contract): the fill carries severity (accent → warning → danger) and the
 * track is a lighter step of the same ramp. Unlimited plans show the value without a bar.
 */
export function UsageMeter({
  label,
  value,
  max,
  valueLabel,
  unlimitedLabel,
}: {
  label: string
  value: number
  max: number | null
  valueLabel: string
  unlimitedLabel: string
}) {
  const ratio = max ? value / max : 0
  const percent = Math.min(100, Math.round(ratio * 100))
  // "Approaching the limit" needs room to approach: 1 of 1 property is simply a full single-hotel plan.
  const tone = !max ? 'accent' : ratio > 1 ? 'danger' : ratio >= 0.85 && max > 3 ? 'warning' : 'accent'
  return (
    <div className="grid grid-cols-1 gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold text-fg">{label}</p>
        <p className="num text-sm text-muted">{max ? valueLabel : unlimitedLabel}</p>
      </div>
      {max ? (
        <div
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-valuetext={valueLabel}
          className={cn(
            'h-2 overflow-hidden rounded-full',
            tone === 'danger' ? 'bg-danger-soft' : tone === 'warning' ? 'bg-warning-soft' : 'bg-accent-soft',
          )}
        >
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-500',
              tone === 'danger' ? 'bg-danger' : tone === 'warning' ? 'bg-warning' : 'bg-accent',
            )}
            style={{ width: `${Math.max(percent, value > 0 ? 3 : 0)}%` }}
          />
        </div>
      ) : (
        <div aria-hidden className="h-2 rounded-full bg-accent-soft" />
      )}
    </div>
  )
}
