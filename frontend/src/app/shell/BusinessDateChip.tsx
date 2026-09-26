import { useTranslation } from 'react-i18next'
import { Tooltip } from '@/components/ui/tooltip'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, normalizeLang } from '@/lib/format'

/** The hotel's operating day, shaped like a key tag (the punched hole) — it moves with the night audit. */
export function BusinessDateChip() {
  const { t, i18n } = useTranslation()
  const { property } = useActiveProperty()
  if (!property) return null
  return (
    <Tooltip content={t('topbar.businessDateHint')}>
      <span
        tabIndex={0}
        aria-label={`${t('topbar.businessDate')}: ${formatDate(property.business_date, 'EEEE d MMMM yyyy', normalizeLang(i18n.language))}`}
        className="inline-flex h-7 shrink-0 items-center gap-2 rounded-full border border-border bg-surface pr-3 pl-1.5 text-[12.5px] shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
      >
        <span aria-hidden className="size-2.5 rounded-full border border-border-strong bg-bg" />
        <span aria-hidden className="eyebrow hidden !text-[10px] xl:inline">
          {t('topbar.businessDate')}
        </span>
        <span aria-hidden className="num font-bold text-fg">
          {formatDate(property.business_date, 'EEE d MMM', normalizeLang(i18n.language))}
        </span>
      </span>
    </Tooltip>
  )
}
