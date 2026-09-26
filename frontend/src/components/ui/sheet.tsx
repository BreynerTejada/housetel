import { cva, type VariantProps } from 'class-variance-authority'
import { X } from 'lucide-react'
import { Dialog as SheetPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { DialogOverlay } from './dialog'

export const Sheet = SheetPrimitive.Root
export const SheetTrigger = SheetPrimitive.Trigger
export const SheetClose = SheetPrimitive.Close

const sheetVariants = cva('fixed z-50 flex flex-col bg-surface text-fg shadow-lg outline-none', {
  variants: {
    side: {
      left: 'inset-y-0 left-0 h-full w-[min(20rem,88vw)] border-r border-border data-[state=closed]:animate-sheet-out-left data-[state=open]:animate-sheet-in-left',
      right:
        'inset-y-0 right-0 h-full w-[min(28rem,92vw)] border-l border-border data-[state=closed]:animate-sheet-out-right data-[state=open]:animate-sheet-in-right',
      bottom:
        'inset-x-0 bottom-0 max-h-[90dvh] rounded-t-2xl border-t border-border data-[state=closed]:animate-sheet-out-bottom data-[state=open]:animate-sheet-in-bottom',
    },
  },
  defaultVariants: { side: 'right' },
})

export function SheetContent({
  className,
  children,
  side,
  hideClose = false,
  ...props
}: ComponentProps<typeof SheetPrimitive.Content> & VariantProps<typeof sheetVariants> & { hideClose?: boolean }) {
  const { t } = useTranslation()
  return (
    <SheetPrimitive.Portal>
      <DialogOverlay />
      <SheetPrimitive.Content className={cn(sheetVariants({ side }), className)} {...props}>
        {children}
        {!hideClose && (
          <SheetPrimitive.Close
            className="absolute top-3.5 right-3.5 rounded-md p-1 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            aria-label={t('actions.close')}
          >
            <X aria-hidden className="size-4" />
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  )
}

export function SheetHeader({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1 border-b border-border px-5 py-4 pr-12', className)} {...props} />
}

export function SheetBody({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('min-h-0 flex-1 overflow-y-auto px-5 py-4', className)} {...props} />
}

export function SheetFooter({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('flex gap-2 border-t border-border px-5 py-3 sm:justify-end', className)} {...props} />
}

export function SheetTitle({ className, ...props }: ComponentProps<typeof SheetPrimitive.Title>) {
  return <SheetPrimitive.Title className={cn('text-base leading-6 font-bold', className)} {...props} />
}

export function SheetDescription({ className, ...props }: ComponentProps<typeof SheetPrimitive.Description>) {
  return <SheetPrimitive.Description className={cn('text-[13px] text-muted', className)} {...props} />
}
