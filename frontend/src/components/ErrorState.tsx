import { CircleAlert, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { Button } from './ui/button'

export function ErrorState({
  error,
  onRetry,
  title,
  className,
}: {
  error?: unknown
  onRetry?: () => void
  title?: string
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <div role="alert" className={cn('flex flex-col items-center gap-2 px-6 py-12 text-center', className)}>
      <span className="grid size-10 place-items-center rounded-full bg-danger-soft text-danger-ink">
        <CircleAlert aria-hidden className="size-5" />
      </span>
      <p className="mt-2 font-semibold text-fg">{title ?? t('states.error')}</p>
      <p className="max-w-sm text-sm text-muted">{errorMessage(error, t)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          <RotateCcw aria-hidden />
          {t('actions.retry')}
        </Button>
      )}
    </div>
  )
}
