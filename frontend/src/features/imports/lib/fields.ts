import type { TFunction } from 'i18next'
import type { Lang } from '@/lib/format'
import type {
  Bilingual,
  DryOutcome,
  FieldGroup,
  FieldSpec,
  ImportKind,
  ImportRow,
  JobDetail,
  JobStatus,
  RowOutcome,
  RowStatus,
} from '../api'

/** Order of the field groups in the mapping step (reservation first, then its stay, guest, money, extra). */
export const GROUP_ORDER: FieldGroup[] = ['main', 'stay', 'guest', 'money', 'extra']

export function groupFields(fields: FieldSpec[]): { group: FieldGroup; fields: FieldSpec[] }[] {
  return GROUP_ORDER.map((group) => ({ group, fields: fields.filter((field) => field.group === group) })).filter(
    (entry) => entry.fields.length > 0,
  )
}

/** The "one of" group a field belongs to (a guest needs a full name or a first name), if any. */
export function oneOfGroup(code: string, oneOf: string[][]): string[] | null {
  return oneOf.find((group) => group.includes(code)) ?? null
}

/** "Llegada" or "Nombre completo o Nombre" for a missing code / group (`a|b`). */
export function missingLabel(t: TFunction, code: string): string {
  const parts = code.split('|').map((part) => t(`fields.${part}`, { ns: 'imports' }))
  return parts.length > 1 ? t('map.oneOfList', { ns: 'imports', a: parts.slice(0, -1).join(', '), b: parts.at(-1) }) : parts[0]
}

export function text(message: Bilingual | Record<string, never> | null | undefined, lang: Lang): string {
  if (!message || !('es' in message)) return ''
  return (lang === 'en' ? message.en : message.es) || message.es || ''
}

export type Tone = 'success' | 'warning' | 'danger' | 'stone' | 'info' | 'accent' | 'neutral'

export const ROW_STATUS_TONE: Record<RowStatus, Tone> = {
  pending: 'neutral',
  valid: 'success',
  warning: 'warning',
  error: 'danger',
  skip: 'stone',
}

export const DRY_TONE: Record<Exclude<DryOutcome, ''>, Tone> = {
  create: 'success',
  update: 'info',
  skip: 'stone',
  fail: 'danger',
}

export const OUTCOME_TONE: Record<Exclude<RowOutcome, ''>, Tone> = {
  created: 'success',
  updated: 'info',
  skipped: 'stone',
  failed: 'danger',
  reverted: 'stone',
}

export const JOB_STATUS_TONE: Record<JobStatus, Tone> = {
  uploaded: 'neutral',
  validated: 'info',
  queued: 'warning',
  running: 'accent',
  completed: 'success',
  failed: 'danger',
  reverted: 'stone',
}

/** Link to what a row created or updated. */
export function targetPath(row: Pick<ImportRow, 'target_type' | 'target_id'>): string | null {
  if (!row.target_id) return null
  switch (row.target_type) {
    case 'bookings.reservation':
      return `/app/reservations/${row.target_id}`
    case 'guests.guest':
      return `/app/guests/${row.target_id}`
    case 'inventory.roomtype':
      return `/app/settings/room-types/${row.target_id}`
    case 'inventory.room':
      return `/app/settings/rooms/${row.target_id}`
    default:
      return null
  }
}

function joinName(first?: string, last?: string): string {
  return [first, last].filter(Boolean).join(' ').trim()
}

/** Main line and secondary line that describe a row (from its normalized values, else its first cells). */
export function describeRow(
  kind: ImportKind,
  row: ImportRow,
  headers: string[],
  formatRange: (start: string, end: string) => string,
): { title: string; detail: string } {
  const data = row.data ?? {}
  if (kind === 'reservations' && (data.guest || data.checkin)) {
    const name = joinName(data.guest?.first_name, data.guest?.last_name)
    const dates = data.checkin && data.checkout ? formatRange(data.checkin, data.checkout) : ''
    const rooms = (data.stays ?? []).map((stay) => (stay.room_label ? `${stay.room_type_code} · ${stay.room_label}` : stay.room_type_code))
    return { title: name || row.external_id, detail: [dates, rooms.join(', ')].filter(Boolean).join(' · ') }
  }
  if (kind === 'guests' && data.guest) {
    const guest = data.guest
    const doc = guest.document_number ? `${guest.document_type ?? ''} ${guest.document_number}`.trim() : ''
    return { title: joinName(guest.first_name, guest.last_name) || row.external_id, detail: [guest.email, doc].filter(Boolean).join(' · ') }
  }
  if (kind === 'room_types' && (data.name || data.code)) {
    const rooms = data.room_numbers?.length ? data.room_numbers.join(', ') : ''
    return { title: [data.code, data.name].filter(Boolean).join(' · '), detail: rooms }
  }
  if (kind === 'rooms' && data.number) {
    return { title: data.number, detail: [data.room_type_code, data.floor].filter(Boolean).join(' · ') }
  }
  const cells = headers.map((header) => row.raw?.[header]).filter(Boolean).slice(0, 3)
  return { title: cells[0] ?? row.external_id ?? '', detail: cells.slice(1).join(' · ') }
}

/** Every row of the file already has its fate (validation) — used to pick the default step of a job. */
export function hasValues(job: JobDetail): boolean {
  return Object.values(job.values ?? {}).some((items) => (items?.length ?? 0) > 0)
}
