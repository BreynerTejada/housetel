import type { LucideIcon } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { cn } from '@/lib/utils'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  icon?: LucideIcon
  disabled?: boolean
}

/**
 * A single choice shown as a segmented control (channel, language, template or free text). It is a radio
 * group for assistive tech: arrows move between options and each one is a radio with its own name.
 */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  disabled = false,
  className,
}: {
  value: T
  onChange: (value: T) => void
  options: SegmentedOption<T>[]
  label: string
  disabled?: boolean
  className?: string
}) {
  return (
    <RadioGroupPrimitive.Root
      value={value}
      onValueChange={(next) => onChange(next as T)}
      aria-label={label}
      disabled={disabled}
      orientation="horizontal"
      className={cn('inline-flex w-fit items-center gap-0.5 rounded-lg border border-border bg-surface-2 p-0.5', className)}
    >
      {options.map(({ value: option, label: text, icon: Icon, disabled: optionDisabled }) => (
        <RadioGroupPrimitive.Item
          key={option}
          value={option}
          disabled={optionDisabled}
          className={cn(
            'inline-flex h-7 items-center justify-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold text-muted transition-colors',
            'hover:text-fg data-[state=checked]:bg-surface data-[state=checked]:text-fg data-[state=checked]:shadow-xs',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:size-4',
          )}
        >
          {Icon && <Icon aria-hidden />}
          {text}
        </RadioGroupPrimitive.Item>
      ))}
    </RadioGroupPrimitive.Root>
  )
}
