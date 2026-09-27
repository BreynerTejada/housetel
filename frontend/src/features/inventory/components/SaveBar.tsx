import { CircleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Sticky bar shown while a form has unsaved changes. */
export function SaveBar({
  visible,
  saving,
  disabled,
  onSave,
  onDiscard,
  problem,
  saveLabel,
}: {
  visible: boolean
  saving?: boolean
  disabled?: boolean
  onSave: () => void
  onDiscard?: () => void
  /** Why saving is disabled (validation), shown instead of "unsaved changes". */
  problem?: string
  saveLabel?: string
}) {
  const { t } = useTranslation('inventory')
  if (!visible) return null
  return (
    <div
      role="region"
      aria-label={t('common.unsaved')}
      className={cn(
        'sticky bottom-4 z-20 mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface/95 px-4 py-3 shadow-lg backdrop-blur',
        'animate-pop-in',
      )}
    >
      <p className={cn('flex min-w-0 flex-1 items-center gap-2 text-[13px] font-semibold', problem ? 'text-danger-ink' : 'text-fg')}>
        {problem ? <CircleAlert aria-hidden className="size-4 shrink-0" /> : <span aria-hidden className="size-2 rounded-full bg-accent" />}
        <span className="truncate">{problem ?? t('common.unsaved')}</span>
      </p>
      {onDiscard && (
        <Button variant="ghost" size="sm" onClick={onDiscard} disabled={saving}>
          {t('common.discard')}
        </Button>
      )}
      <Button variant="primary" size="sm" onClick={onSave} loading={saving} disabled={disabled}>
        {saveLabel ?? t('common:actions.saveChanges')}
      </Button>
    </div>
  )
}
