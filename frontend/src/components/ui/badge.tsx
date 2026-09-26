import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs leading-4 font-semibold [&_svg]:size-3',
  {
    variants: {
      tone: {
        neutral: 'border-border bg-surface-2 text-muted',
        accent: 'border-transparent bg-accent-soft text-accent-ink',
        success: 'border-transparent bg-success-soft text-success-ink',
        warning: 'border-transparent bg-warning-soft text-warning-ink',
        danger: 'border-transparent bg-danger-soft text-danger-ink',
        info: 'border-transparent bg-info-soft text-info-ink',
        stone: 'border-transparent bg-stone-soft text-stone-ink',
        outline: 'border-border-strong bg-transparent text-fg',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>['tone']>

export function Badge({ className, tone, ...props }: ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}
