import { useTranslation } from 'react-i18next'
import { normalizeLang } from '@/lib/format'
import type { WeekdayAdjustments } from '../api'
import { adjustmentEntries, signedPercent } from '../lib/plans'

/** Formatter of weekday adjustments: "vie +15 % · sáb +15 %" (or "Sin ajustes"). */
export function useAdjustmentSummary() {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  return (adjustments: WeekdayAdjustments | null | undefined) => {
    const entries = adjustmentEntries(adjustments)
    if (entries.length === 0) return t('plans.adjustments.none')
    return entries.map(([key, value]) => `${t(`daysAbbr.${key}`)} ${signedPercent(value, lang)}`).join(' · ')
  }
}
