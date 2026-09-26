import { Label as LabelPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn(
        'text-[13px] leading-5 font-semibold text-fg select-none peer-disabled:opacity-60 group-data-[disabled=true]:opacity-60',
        className,
      )}
      {...props}
    />
  )
}
