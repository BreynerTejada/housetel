import { Tabs as TabsPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export const Tabs = TabsPrimitive.Root

/** Underlined tabs on a hairline, the default for page sections. */
export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn('flex items-center gap-5 overflow-x-auto border-b border-border [scrollbar-width:none]', className)}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'relative -mb-px inline-flex h-10 shrink-0 items-center gap-2 border-b-2 border-transparent text-sm font-semibold text-muted transition-colors',
        'hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:opacity-50',
        '[&_svg]:size-4',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn('pt-5 outline-none', className)} {...props} />
}
