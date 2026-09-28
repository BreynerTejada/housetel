import type { BadgeTone } from '@/components/ui/badge'
import type { HealthStatus, InvoiceStatus, SireStatus, TraStatus } from '../api'

/** Badge tones of the legal states (design tokens: sage = done, sand = waiting on us, clay = problem). */
export const INVOICE_TONES: Record<InvoiceStatus | 'not_issued', BadgeTone> = {
  draft: 'neutral',
  issued: 'info',
  accepted: 'success',
  rejected: 'danger',
  cancelled: 'stone',
  error: 'warning',
  not_issued: 'warning',
}

export const SIRE_TONES: Record<SireStatus, BadgeTone> = {
  generated: 'warning',
  submitted: 'info',
  acknowledged: 'success',
}

export const TRA_TONES: Record<TraStatus | 'not_registered', BadgeTone> = {
  pending: 'warning',
  registered: 'success',
  error: 'danger',
  not_registered: 'neutral',
}

export const HEALTH_TONES: Record<HealthStatus, BadgeTone> = {
  ok: 'success',
  warning: 'warning',
  critical: 'danger',
  missing: 'danger',
}

export const RETRYABLE: InvoiceStatus[] = ['draft', 'error', 'rejected', 'issued']
export const VOIDABLE: InvoiceStatus[] = ['issued', 'accepted']

/** "SETT128" → file names like the backend's (`factura-SETT128.pdf`). */
export function invoiceFileName(kind: 'invoice' | 'credit_note', number: string, extension: string): string {
  return `${kind === 'credit_note' ? 'nota-credito' : 'factura'}-${number || 'borrador'}.${extension}`
}

/** CUFE/CUDE (96 hex characters) in groups of eight, the way people compare hashes by eye. */
export function hashGroups(value: string, size = 8): string[] {
  const groups: string[] = []
  for (let index = 0; index < value.length; index += size) groups.push(value.slice(index, index + size))
  return groups
}

/** "$ 58,2 M" for KPI tiles (the full amount goes in the tooltip). */
export function compactMoney(value: string | number, lang: 'es' | 'en', currency = 'COP'): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'
  return new Intl.NumberFormat(lang === 'es' ? 'es-CO' : 'en-US', {
    style: 'currency',
    currency,
    notation: Math.abs(amount) >= 1_000_000 ? 'compact' : 'standard',
    maximumFractionDigits: Math.abs(amount) >= 1_000_000 ? 1 : 0,
  }).format(amount)
}
