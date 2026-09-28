import type { TFunction, i18n as I18n } from 'i18next'
import { formatDate, formatNumber, normalizeLang, type Lang } from '@/lib/format'
import type { I18nText } from '../api'

/** Label of an i18n key of the `control` namespace, or `fallback` when the key does not exist. */
function known(t: TFunction, i18n: I18n, key: string, fallback: string): string {
  return i18n.exists(key, { ns: 'control' }) ? t(key, { ns: 'control' }) : fallback
}

export function humanize(key: string): string {
  const text = key.replace(/[._]+/g, ' ').trim()
  return text ? text[0].toUpperCase() + text.slice(1) : key
}

/** "bookings.room_assigned" → "Habitación asignada"; automation runs share one label. */
export function actionLabel(t: TFunction, i18n: I18n, action: string): string {
  if (action.startsWith('automation.')) return t('actionLabels.automationRun', { ns: 'control' })
  return known(t, i18n, `actionLabels.${action}`, humanize(action.split('.').slice(1).join(' ') || action))
}

export function appLabel(t: TFunction, i18n: I18n, app: string): string {
  return known(t, i18n, `apps.${app}`, humanize(app))
}

export function alertKindLabel(t: TFunction, i18n: I18n, kind: string): string {
  return known(t, i18n, `alertKinds.${kind}`, humanize(kind))
}

export function localized(text: I18nText | undefined, lang: string): string {
  if (!text) return ''
  return normalizeLang(lang) === 'en' ? text.en || text.es : text.es || text.en
}

export function formatDuration(ms: number | null | undefined, t: TFunction, lang: Lang): string {
  if (ms === null || ms === undefined) return t('common.empty', { ns: 'control' })
  if (ms < 1000) return t('common.milliseconds', { ns: 'control', value: formatNumber(ms, lang, 0) })
  if (ms < 60_000) return t('common.seconds', { ns: 'control', value: formatNumber(ms / 1000, lang, 1) })
  return t('common.minutes', { ns: 'control', value: formatNumber(ms / 60_000, lang, 1) })
}

/** Time of day of an ISO datetime in the user's clock ("21:04"). */
export function clockTime(value: string | null | undefined, lang: Lang): string {
  return value ? formatDate(value, 'HH:mm', lang) : '—'
}

/** Readable value for before/after tables (JSON values of any shape). */
export function displayValue(value: unknown, t: TFunction): string {
  if (value === null || value === undefined || value === '') return t('common.empty', { ns: 'control' })
  if (value === true) return t('common.yes', { ns: 'control' })
  if (value === false) return t('common.no', { ns: 'control' })
  if (Array.isArray(value)) return value.length ? value.map((item) => displayValue(item, t)).join(', ') : t('common.empty', { ns: 'control' })
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** "status" → "Estado"; nested keys ("config.environment", "params.days_ahead") join their known parts. */
export function fieldLabel(t: TFunction, i18n: I18n, key: string): string {
  const parts = key.split('.')
  return parts.map((part) => known(t, i18n, `fieldLabels.${part}`, humanize(part))).join(' · ')
}

/** Calendar day (browser time) of an ISO datetime, `YYYY-MM-DD`: the audit timeline groups by it. */
export function dayKey(value: string): string {
  return formatDate(value, 'yyyy-MM-dd')
}

/** "Hoy", "Ayer" or "martes 22 de septiembre" for a `dayKey`. */
export function dayHeading(t: TFunction, lang: Lang, key: string, today: Date = new Date()): string {
  const todayKey = formatDate(today, 'yyyy-MM-dd')
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (key === todayKey) return t('audit.today', { ns: 'control' })
  if (key === formatDate(yesterday, 'yyyy-MM-dd')) return t('audit.yesterday', { ns: 'control' })
  const sameYear = key.slice(0, 4) === todayKey.slice(0, 4)
  const pattern = lang === 'en' ? (sameYear ? 'EEEE, MMMM d' : 'EEEE, MMMM d, yyyy') : sameYear ? "EEEE d 'de' MMMM" : "EEEE d 'de' MMMM 'de' yyyy"
  return formatDate(key, pattern, lang)
}

/** Who did it, for people and machines alike ("Valentina Rojas", "Auditoría nocturna", "Canal"). */
export function actorName(event: { actor: { name: string } | null; actor_label: string; source: string }, t: TFunction): string {
  if (event.actor) return event.actor.name
  return event.actor_label || t(`sources.${event.source}`, { ns: 'control' })
}

/** Plain text of a short message that may carry light Markdown (the AI daily brief uses **bold** and `code`). */
export function plainText(value: string): string {
  return value.replace(/\*\*(.+?)\*\*/g, '$1').replace(/__(.+?)__/g, '$1').replace(/`([^`]+)`/g, '$1')
}

/** Readable value of a known enumeration in audit changes (status, mode, source, severity), else `displayValue`. */
export function valueLabel(t: TFunction, i18n: I18n, field: string, value: unknown): string {
  if (typeof value === 'string' && value) {
    const leaf = field.split('.').pop() ?? field
    const candidates =
      leaf === 'status' || leaf.endsWith('_status')
        ? [`control:runStatus.${value}`, `common:status.reservation.${value}`, `common:status.payment.${value}`, `common:status.room.${value}`]
        : leaf === 'mode'
          ? [`control:integrations.mode.${value}`]
          : leaf === 'source'
            ? [`control:sources.${value}`]
            : leaf === 'severity'
              ? [`control:severity.${value}`]
              : []
    const key = candidates.find((candidate) => i18n.exists(candidate))
    if (key) return t(key)
  }
  return displayValue(value, t)
}
