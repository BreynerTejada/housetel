import { Tooltip as TooltipPrimitive } from 'radix-ui'
import type { ComponentProps, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export const TooltipProvider = TooltipPrimitive.Provider
export const TooltipRoot = TooltipPrimitive.Root
export const TooltipTrigger = TooltipPrimitive.Trigger

export function TooltipContent({ className, sideOffset = 6, children, ...props }: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          'z-50 max-w-72 rounded-md bg-fg px-2.5 py-1.5 text-xs leading-4 font-medium text-bg shadow-md',
          'data-[state=closed]:animate-fade-out data-[state=delayed-open]:animate-fade-in',
          className,
        )}
        {...props}
      >
        {children}
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

/** Shorthand: `<Tooltip content="…"><Button …/></Tooltip>` (needs the provider from AppProviders). */
export function Tooltip({
  content,
  children,
  side,
  align,
}: {
  content: ReactNode
  children: ReactNode
  side?: ComponentProps<typeof TooltipPrimitive.Content>['side']
  align?: ComponentProps<typeof TooltipPrimitive.Content>['align']
}) {
  return (
    <TooltipRoot>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} align={align}>
        {content}
      </TooltipContent>
    </TooltipRoot>
  )
}
