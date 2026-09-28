import { Minus, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

/** A small whole-number field with − / + buttons (guests of a booking). */
export function Stepper({
  id,
  label,
  value,
  min,
  max,
  disabled = false,
  onChange,
}: {
  id: string
  label: string
  value: number
  min: number
  max: number
  disabled?: boolean
  onChange: (value: number) => void
}) {
  const { t } = useTranslation('calendar')
  const clamp = (next: number) => Math.min(max, Math.max(min, next))
  const button =
    'grid h-full w-9 shrink-0 place-items-center text-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:pointer-events-none disabled:opacity-35'
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className={cn('flex h-9 items-center overflow-hidden rounded-md border border-border bg-surface shadow-xs', disabled && 'bg-surface-2 opacity-60')}>
        <button type="button" className={button} aria-label={t('create.decrease', { label: label.toLocaleLowerCase() })} disabled={disabled || value <= min} onClick={() => onChange(clamp(value - 1))}>
          <Minus aria-hidden className="size-3.5" />
        </button>
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          value={value}
          disabled={disabled}
          onChange={(event) => {
            const next = Number.parseInt(event.target.value, 10)
            if (Number.isFinite(next)) onChange(clamp(next))
          }}
          className="num h-full w-full min-w-0 bg-transparent text-center text-sm font-bold text-fg outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <button type="button" className={button} aria-label={t('create.increase', { label: label.toLocaleLowerCase() })} disabled={disabled || value >= max} onClick={() => onChange(clamp(value + 1))}>
          <Plus aria-hidden className="size-3.5" />
        </button>
      </div>
    </div>
  )
}
