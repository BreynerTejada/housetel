import type { BadgeTone } from '@/components/ui/badge'
import type { AriStatus, LogStatus, SimBookingStatus, SimPmsStatus } from '../api'

/** Kinds of sync log entries the backend writes (`SyncLog.kind`); anything else reads as "other". */
const LOG_KINDS = new Set([
  'ari',
  'booking_new',
  'booking_modified',
  'booking_cancelled',
  'booking_history',
  'booking_pull',
  'booking_ack',
  'ical_import',
  'test',
])

/** i18n key (namespace `channels`) of a sync log kind. */
export function logKindKey(kind: string): string {
  return `log.kinds.${LOG_KINDS.has(kind) ? kind : 'other'}`
}

export const LOG_STATUS_TONE: Record<LogStatus, BadgeTone> = {
  success: 'success',
  warning: 'warning',
  error: 'danger',
  skipped: 'neutral',
}

export const ARI_STATUS_TONE: Record<AriStatus, BadgeTone> = {
  pending: 'warning',
  sending: 'info',
  sent: 'success',
  failed: 'danger',
}

export const SIM_STATUS_TONE: Record<SimBookingStatus, BadgeTone> = {
  new: 'info',
  modified: 'warning',
  cancelled: 'stone',
}

export const PMS_STATUS_TONE: Record<SimPmsStatus, BadgeTone> = {
  pending: 'warning',
  imported: 'success',
  failed: 'danger',
}

/** Countries offered for a guest invented in the OTA simulator (ISO-2). */
export const GUEST_COUNTRIES = ['CO', 'US', 'ES', 'MX', 'AR', 'BR', 'CL', 'PE', 'EC', 'FR', 'DE', 'GB', 'CA', 'IT', 'NL'] as const

/** Readable pseudo-domain of a simulated OTA extranet (only a visual cue that the screen belongs to the OTA). */
export function otaDomain(channel: string): string {
  if (channel === 'booksim') return 'extranet.booksim.test'
  if (channel === 'airsim') return 'hosts.airsim.test'
  return 'app.channex.test'
}
