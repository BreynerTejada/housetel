import type { TFunction } from 'i18next'
import { formatMoney, type Amount } from '@/lib/format'
import type { Bed, CancellationPolicy, I18nText } from '../api'

/** Money inside sentences and button labels ("Reservar y pagar $ 761.600"), with regular spaces. */
export function moneyLabel(value: Amount, currency = 'COP'): string {
  return formatMoney(value, currency).replace(/\s/g, ' ')
}

/** The text in `lang`, then Spanish, then any language (backend `apps.core.i18n.t`). */
export function tr(value: I18nText | string | null | undefined, lang: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  const key = lang.startsWith('en') ? 'en' : 'es'
  return value[key] || value.es || value.en || ''
}

export interface PolicySummary {
  /** free: free cancellation for a while · partial: always a fee · strict: nothing is refunded */
  tone: 'free' | 'partial' | 'strict'
  title: string
  detail: string
}

function percentValue(value: string): string {
  const n = Number(value)
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : value
}

/** What a cancellation policy means for the guest, in one title and one sentence. */
export function policySummary(policy: CancellationPolicy | null | undefined, t: TFunction): PolicySummary {
  if (!policy) return { tone: 'free', title: t('marketplace:policy.noPolicy'), detail: t('marketplace:policy.noPolicyDetail') }
  if (policy.non_refundable) {
    return { tone: 'strict', title: t('marketplace:policy.nonRefundable'), detail: t('marketplace:policy.always.full') }
  }
  const value = percentValue(policy.penalty_value)
  const hours = policy.free_until_hours_before
  if (hours > 0) {
    const when = hours % 24 === 0 ? t('marketplace:policy.days', { count: hours / 24 }) : t('marketplace:policy.hours', { count: hours })
    return {
      tone: 'free',
      title: t('marketplace:policy.free', { when }),
      detail: t(`marketplace:policy.after.${policy.penalty_type}`, { value }),
    }
  }
  return { tone: 'partial', title: t('marketplace:policy.withFee'), detail: t(`marketplace:policy.always.${policy.penalty_type}`, { value }) }
}

export function guestsLabel(adults: number, children: number, t: TFunction): string {
  const parts = [t('marketplace:guests.adults', { count: adults })]
  if (children > 0) parts.push(t('marketplace:guests.children', { count: children }))
  return parts.join(' · ')
}

const KNOWN_BEDS = ['single', 'twin', 'double', 'queen', 'king', 'bunk', 'sofa_bed', 'crib']

export function bedsLabel(beds: Bed[] | null | undefined, t: TFunction): string {
  return (beds ?? [])
    .filter((bed) => bed.count > 0)
    .map((bed) => (KNOWN_BEDS.includes(bed.type) ? t(`marketplace:beds.${bed.type}`, { count: bed.count }) : `${bed.count} × ${bed.type}`))
    .join(' · ')
}
