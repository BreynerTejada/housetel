import type { BadgeTone } from '@/components/ui/badge'
import type {
  BillingCycle,
  CommissionStatus,
  I18nText,
  InvoiceStatus,
  OrganizationStatus,
  SettlementStatus,
  SubscriptionStatus,
} from './api'

/** `{es, en}` API text in the UI language (falls back to Spanish, then any value). */
export function pickText(value: I18nText | string | null | undefined, lang: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  const key = lang.startsWith('en') ? 'en' : 'es'
  return value[key] || value.es || value.en || ''
}

/** Status colors follow the design system: good = success, needs attention = warning, blocked = danger. */
export const SUBSCRIPTION_TONE: Record<SubscriptionStatus, BadgeTone> = {
  trialing: 'info',
  active: 'success',
  past_due: 'warning',
  suspended: 'danger',
  cancelled: 'stone',
}

export const ORGANIZATION_TONE: Record<OrganizationStatus, BadgeTone> = {
  trial: 'info',
  active: 'success',
  past_due: 'warning',
  suspended: 'danger',
  cancelled: 'stone',
}

export const INVOICE_TONE: Record<InvoiceStatus, BadgeTone> = {
  open: 'warning',
  paid: 'success',
  void: 'stone',
  failed: 'danger',
}

export const COMMISSION_TONE: Record<CommissionStatus, BadgeTone> = {
  pending: 'info',
  settled: 'success',
  reversed: 'stone',
}

export const SETTLEMENT_TONE: Record<SettlementStatus, BadgeTone> = {
  open: 'warning',
  invoiced: 'info',
  paid: 'success',
}

/** Compact money for tiles and axes ("$ 1,2 M"). */
export function compactMoney(value: string | number, lang: string): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat(lang.startsWith('en') ? 'en-US' : 'es-CO', {
    style: 'currency',
    currency: 'COP',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(n)
}

/** `2026-09` → localized short month ("sep 26" / "Sep 26"). */
export function monthLabel(month: string, lang: string, style: 'short' | 'long' = 'short'): string {
  const [year, m] = month.split('-').map(Number)
  if (!year || !m) return month
  const date = new Date(year, m - 1, 1)
  return new Intl.DateTimeFormat(lang.startsWith('en') ? 'en-US' : 'es-CO', {
    month: style,
    year: style === 'short' ? '2-digit' : 'numeric',
  }).format(date)
}

/** Price of a plan for a billing cycle (API decimal string). */
export function planPrice(plan: { price_monthly: string; price_yearly: string }, cycle: BillingCycle): string {
  return cycle === 'yearly' ? plan.price_yearly : plan.price_monthly
}
