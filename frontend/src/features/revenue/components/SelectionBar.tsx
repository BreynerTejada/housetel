import { ArrowDown, ArrowUp, Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import type { Decision } from '../api'

export interface SelectionBarProps {
  count: number
  up: number
  down: number
  pending: Decision | null
  onDecide: (decision: Decision) => void
  onClear: () => void
}

/** Mass decision on the selected nights; stays at the bottom of the screen while the map scrolls. */
export function SelectionBar({ count, up, down, pending, onDecide, onClear }: SelectionBarProps) {
  const { t } = useTranslation('revenue')
  return (
    <section
      aria-label={t('selection.label')}
      className="sticky bottom-3 z-40 mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border-strong bg-surface px-4 py-3 shadow-lg animate-pop-in"
    >
      <div className="min-w-0 flex-1" aria-live="polite">
        <p className="text-sm font-bold text-fg">{t('selection.count', { count })}</p>
        <p className="flex items-center gap-3 text-xs text-muted">
          <span className="flex items-center gap-1">
            <ArrowUp aria-hidden className="size-3" />
            {t('kpis.up', { count: up })}
          </span>
          <span className="flex items-center gap-1">
            <ArrowDown aria-hidden className="size-3" />
            {t('kpis.down', { count: down })}
          </span>
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onClear} disabled={pending !== null} aria-label={t('selection.clear')}>
          <X aria-hidden />
          {t('selection.clearShort')}
        </Button>
        <Button size="sm" onClick={() => onDecide('reject')} loading={pending === 'reject'} disabled={pending !== null}>
          {t('actions.reject')}
        </Button>
        <Button variant="primary" size="sm" onClick={() => onDecide('approve')} loading={pending === 'approve'} disabled={pending !== null}>
          <Check aria-hidden />
          {t('actions.approve')}
        </Button>
      </div>
    </section>
  )
}
