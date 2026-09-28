import { Minus, Plus } from 'lucide-react'
import { useId } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Whole-number stepper (adults, children, nights): the value between a "remove" and an "add" button. */
export function Counter({
  label,
  hint,
  value,
  onChange,
  min = 0,
  max = 99,
  addLabel,
  removeLabel,
  className,
}: {
  label: string
  hint?: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  addLabel: string
  removeLabel: string
  className?: string
}) {
  const labelId = useId()
  return (
    <div role="group" aria-labelledby={labelId} className={cn('flex items-center justify-between gap-4', className)}>
      <div className="min-w-0">
        <p id={labelId} className="font-semibold text-fg">
          {label}
        </p>
        {hint && <p className="text-[13px] text-muted">{hint}</p>}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="icon-sm" aria-label={removeLabel} disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))}>
          <Minus aria-hidden />
        </Button>
        <output aria-live="polite" className="num w-8 text-center text-[15px] font-bold text-fg">
          {value}
        </output>
        <Button variant="secondary" size="icon-sm" aria-label={addLabel} disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))}>
          <Plus aria-hidden />
        </Button>
      </div>
    </div>
  )
}
