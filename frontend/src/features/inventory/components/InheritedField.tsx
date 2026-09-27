import { Link2, PencilLine, RotateCcw } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * One attribute of a room that may come from its category. Inherited: the category value, muted, on a
 * dashed "thread" with "Heredado de <categoría>" and an "Override" action. Overridden: the room's own
 * control on a solid terracotta rule, tagged "Propio", with the category value as a hint and a
 * "Restore inheritance" action. `locked` (e.g. dorm occupancy) only shows the inherited value.
 */
export function InheritedField({
  label,
  categoryName,
  overridden,
  inheritedText,
  inheritedDisplay,
  control,
  onOverride,
  onRestore,
  error,
  locked,
  lockedHint,
}: {
  label: string
  categoryName: string
  overridden: boolean
  /** Plain text of the category value (hint and default display). */
  inheritedText: string
  inheritedDisplay?: ReactNode
  control: (labelId: string) => ReactNode
  onOverride: () => void
  onRestore: () => void
  error?: string
  locked?: boolean
  lockedHint?: string
}) {
  const { t } = useTranslation('inventory')
  const labelId = useId()
  const errorId = `${labelId}-error`

  return (
    <div
      role="group"
      aria-labelledby={labelId}
      aria-describedby={error ? errorId : undefined}
      className={cn(
        'grid gap-x-6 gap-y-2 border-l-2 py-3 pr-1 pl-4 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] sm:items-start',
        overridden ? 'border-accent' : 'border-dashed border-border-strong',
        error && 'border-danger',
      )}
    >
      <div id={labelId} className="pt-2 text-[13px] font-semibold text-fg">
        {label}
      </div>

      <div className="min-w-0">
        {overridden ? (
          control(labelId)
        ) : (
          <div className="flex min-h-9 items-center text-muted">{inheritedDisplay ?? inheritedText}</div>
        )}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-subtle">
          {overridden ? (
            <>
              <span className="rounded-full bg-accent-soft px-1.5 py-px text-2xs font-bold text-accent-ink">{t('common.own')}</span>
              <span>{t('common.categorySays', { value: inheritedText })}</span>
            </>
          ) : (
            <span className="inline-flex items-center gap-1">
              <Link2 aria-hidden className="size-3" />
              {locked && lockedHint ? lockedHint : t('common.inheritedFrom', { category: categoryName })}
            </span>
          )}
        </p>
        {error && (
          <p id={errorId} className="mt-1 text-xs font-medium text-danger-ink" aria-live="polite">
            {error}
          </p>
        )}
      </div>

      <div className="sm:pt-0.5">
        {!locked &&
          (overridden ? (
            <Button variant="ghost" size="sm" onClick={onRestore} aria-label={t('common.restoreField', { field: label })}>
              <RotateCcw aria-hidden />
              {t('common.restore')}
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={onOverride} aria-label={t('common.overrideField', { field: label })}>
              <PencilLine aria-hidden />
              {t('common.override')}
            </Button>
          ))}
      </div>
    </div>
  )
}
