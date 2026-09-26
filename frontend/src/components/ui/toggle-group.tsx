import { ToggleGroup as ToggleGroupPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** Segmented control (e.g. 7 / 14 / 30 days, density). */
export function ToggleGroup({ className, ...props }: ComponentProps<typeof ToggleGroupPrimitive.Root>) {
  return (
    <ToggleGroupPrimitive.Root
      className={cn('inline-flex items-center gap-0.5 rounded-lg border border-border bg-surface-2 p-0.5', className)}
      {...props}
    />
  )
}

export function ToggleGroupItem({ className, ...props }: ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return (
    <ToggleGroupPrimitive.Item
      className={cn(
        'inline-flex h-7 items-center justify-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold text-muted transition-colors',
        'hover:text-fg data-[state=on]:bg-surface data-[state=on]:text-fg data-[state=on]:shadow-xs',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:opacity-50 [&_svg]:size-4',
        className,
      )}
      {...props}
    />
  )
}
