import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { LEGEND_SOURCES, SOURCE_INK } from '../lib/text'

/** What the ink under each price means, plus the weekend and holiday marks of the date header. */
export function SourceLegend({ className }: { className?: string }) {
  const { t } = useTranslation('rates')
  return (
    <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted', className)}>
      <span className="eyebrow">{t('legend.title')}</span>
      {LEGEND_SOURCES.map((source) => {
        const ink = SOURCE_INK[source]
        return (
          <span key={source} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className={cn('h-[3px] w-4 rounded-full', !ink && 'bg-border-strong/60')}
              style={ink ? { background: ink } : undefined}
            />
            {t(`sources.${source}`)}
          </span>
        )
      })}
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-3 rounded-sm border border-border bg-surface-2" />
        {t('legend.weekend')}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-1.5 rounded-full bg-accent" />
        {t('legend.holiday')}
      </span>
    </div>
  )
}
