import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export const fieldBase = [
  'w-full min-w-0 rounded-md border border-border bg-surface text-fg shadow-xs transition-[border-color,box-shadow]',
  'placeholder:text-subtle hover:border-border-strong',
  'focus-visible:outline-none focus-visible:border-accent focus-visible:ring-3 focus-visible:ring-accent/15',
  'aria-invalid:border-danger aria-invalid:focus-visible:ring-danger/15',
  'disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-60',
].join(' ')

export function Input({ className, type = 'text', ...props }: ComponentProps<'input'>) {
  return <input type={type} className={cn(fieldBase, 'h-9 px-3 text-sm', className)} {...props} />
}
