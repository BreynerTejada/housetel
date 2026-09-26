import { LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Skeleton } from './ui/skeleton'

/** `spinner` for panels, `rows` for lists and tables while the first page loads. */
export function LoadingState({
  label,
  variant = 'spinner',
  rows = 5,
  className,
}: {
  label?: string
  variant?: 'spinner' | 'rows'
  rows?: number
  className?: string
}) {
  const { t } = useTranslation()
  const text = label ?? t('states.loading')
  if (variant === 'rows') {
    return (
      <div role="status" aria-label={text} className={cn('grid gap-2 p-4', className)}>
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-9" style={{ opacity: 1 - i * (0.6 / rows) }} />
        ))}
      </div>
    )
  }
  return (
    <div role="status" className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted', className)}>
      <LoaderCircle aria-hidden className="size-4 animate-spin text-accent" />
      {text}
    </div>
  )
}
