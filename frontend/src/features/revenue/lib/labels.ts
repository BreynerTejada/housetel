import type { TFunction } from 'i18next'
import { formatDate, formatMoney, formatNumber, type Lang } from '@/lib/format'
import type { CalendarCell, Reason, RecommendationStatus } from '../api'
import { signedPercent } from './format'

/** "20 %" / "88,5 %" — a plain percentage as `lang` writes it. */
export function percent(value: string | number, lang: Lang): string {
  return `${formatNumber(Number(value), lang, 2)} %`
}

/** Status in words (lower case, for sentences and screen readers). */
export function statusText(t: TFunction, status: RecommendationStatus): string {
  return t(`revenue:status.${status}`)
}

/** "subir +12 % (de $ 320.000 a $ 358.000)". */
export function changePhrase(t: TFunction, cell: Pick<CalendarCell, 'change_percent' | 'current_price' | 'recommended_price'>, lang: Lang, currency: string): string {
  return t(Number(cell.change_percent) >= 0 ? 'revenue:map.raise' : 'revenue:map.lower', {
    percent: signedPercent(cell.change_percent, lang),
    from: formatMoney(cell.current_price, currency),
    to: formatMoney(cell.recommended_price, currency),
  })
}

export function shortDate(date: string, lang: Lang): string {
  return formatDate(date, 'EEE d MMM', lang)
}

export interface ReasonLine {
  /** Rule name, or the kind of limit. */
  title: string
  /** What the rule saw on that night ("Con 88 % de ocupación"). */
  detail: string
  /** "+15 %" for rules, the resulting price for limits. */
  value: string
  applied: boolean
}

/** Words for one reason of a recommendation. */
export function reasonLine(t: TFunction, reason: Reason, lang: Lang, currency: string): ReasonLine {
  if (reason.type === 'limit') {
    const price = formatMoney(reason.price, currency)
    if (reason.kind === 'max_daily_change') {
      return {
        title: t('revenue:reasons.maxDailyChange', { percent: percent(reason.percent ?? '0', lang) }),
        detail: t('revenue:reasons.maxDailyChangeDetail'),
        value: price,
        applied: true,
      }
    }
    return {
      title: t(reason.kind === 'min_price' ? 'revenue:reasons.minPrice' : 'revenue:reasons.maxPrice'),
      detail: t(reason.kind === 'min_price' ? 'revenue:reasons.minPriceDetail' : 'revenue:reasons.maxPriceDetail'),
      value: price,
      applied: true,
    }
  }
  const detail = reason.detail ?? {}
  let text: string
  switch (reason.kind) {
    case 'occupancy':
      text = t('revenue:reasons.occupancy', { value: percent(detail.occupancy ?? '0', lang) })
      break
    case 'lead_time':
      text =
        detail.window === 'early_bird'
          ? t('revenue:reasons.earlyBird', { count: detail.lead_days ?? 0 })
          : detail.lead_days === 0
            ? t('revenue:reasons.lastMinuteToday')
            : t('revenue:reasons.lastMinute', { count: detail.lead_days ?? 0 })
      break
    case 'day_of_week':
      text = t(`revenue:weekdays.${detail.weekday ?? 'mon'}`)
      break
    case 'holiday': {
      const name = (lang === 'en' ? detail.name_en : detail.name_es) || detail.name_es || ''
      text = t(detail.bridge ? 'revenue:reasons.bridge' : 'revenue:reasons.holiday', { name })
      break
    }
    case 'event':
      text = t('revenue:reasons.event', { name: detail.name || reason.name })
      break
    default:
      text = ''
  }
  return {
    title: reason.name,
    detail: reason.applied ? text : `${text} · ${t('revenue:reasons.notApplied')}`,
    value: signedPercent(reason.adjust, lang),
    applied: reason.applied,
  }
}
