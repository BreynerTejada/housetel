import type { TFunction, i18n as I18n } from 'i18next'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, formatMoney, normalizeLang, type Lang } from '@/lib/format'
import type { Alert } from '../api'

/**
 * Alerts in the viewer's language (plan P6). The backend stores each alert's title and message in Spanish, plus
 * `kind` and `data`; here `control:alertText.<kind>.title|message` are filled with that data. When a kind has
 * no text of its own, or its data lacks a value the text needs (alerts raised before their producer stored
 * it), the stored text is shown as it is.
 */
export interface AlertText {
  title: string
  message: string
}

type Value = string | number | undefined
type Vars = Record<string, Value>

interface Ctx {
  alert: Alert
  data: Record<string, unknown>
  t: TFunction
  i18n: I18n
  lang: Lang
  currency: string
}

const NS = 'control'
const PLURAL_SUFFIXES = ['', '_zero', '_one', '_two', '_few', '_many', '_other']
const PLACEHOLDER = /\{\{\s*([\w.]+)/g
/** Booking codes (`HT-7PKAQA`): a few producers keep them only in the stored title. */
const RESERVATION_CODE = /\bHT-[A-Z0-9]{4,10}\b/

function text(value: unknown): string | undefined {
  if (typeof value === 'string') return value.trim() || undefined
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter((item): item is string => Boolean(item)) : []
}

function count(value: unknown): number | undefined {
  if (Array.isArray(value)) return value.length
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : NaN
  return Number.isFinite(number) ? number : undefined
}

/** A provider's error as the end of a sentence we continue ("…could complete." → "…could complete"). */
function errorText(value: unknown): string | undefined {
  return text(value)?.replace(/[\s.]+$/, '') || undefined
}

function i18nText(value: unknown, lang: Lang): string | undefined {
  if (!value || typeof value !== 'object') return text(value)
  const item = value as Record<string, unknown>
  return text(item[lang]) ?? text(item.es) ?? text(item.en)
}

function code(ctx: Ctx): string | undefined {
  return (
    text(ctx.data.code) ??
    text(ctx.data.reservation_code) ??
    ctx.alert.title.match(RESERVATION_CODE)?.[0] ??
    ctx.alert.message.match(RESERVATION_CODE)?.[0]
  )
}

function money(ctx: Ctx, value: unknown, { absolute = false } = {}): string | undefined {
  const number = count(value)
  if (number === undefined) return undefined
  return formatMoney(absolute ? Math.abs(number) : number, ctx.currency)
}

/** "lunes 28 de septiembre" / "Monday, September 28" (a calendar day `YYYY-MM-DD`). */
function day(ctx: Ctx, value: unknown): string | undefined {
  const iso = text(value)
  if (!iso) return undefined
  return formatDate(iso, ctx.lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", ctx.lang)
}

/** "28 sep" / "Sep 28". */
function shortDay(ctx: Ctx, value: unknown): string | undefined {
  const iso = text(value)
  if (!iso) return undefined
  return formatDate(iso, ctx.lang === 'en' ? 'MMM d' : "d 'de' MMM", ctx.lang)
}

/** Label of an i18n key of any namespace, or `fallback` when the key does not exist. */
function label(ctx: Ctx, key: string, fallback: string | undefined): string | undefined {
  return ctx.i18n.exists(key) ? ctx.t(key) : fallback
}

function kindLabel(ctx: Ctx, kind: unknown): string | undefined {
  const value = text(kind)
  return value ? label(ctx, `control:integrations.kinds.${value}.title`, value) : undefined
}

function joinCodes(ctx: Ctx, values: string[]): string | undefined {
  if (!values.length) return undefined
  return new Intl.ListFormat(ctx.lang === 'en' ? 'en-US' : 'es-CO', { style: 'long', type: 'conjunction' }).format(values)
}

/** Variables of each kind's texts, from the alert's `data` (a value that is missing leaves the stored text). */
const VARIABLES: Record<string, (ctx: Ctx) => Vars> = {
  // --- AI (anomaly scan, daily brief, provider, chatbot)
  unguaranteed_arrival: (c) => ({ code: code(c), guest: text(c.data.guest), checkin: day(c, c.data.checkin) }),
  duplicate_payment: (c) => ({
    target: text(c.data.code) ?? (c.data.code === '' ? c.t('control:alertText.common.houseFolio') : undefined),
    amount: money(c, c.data.amount),
    method: text(c.data.method) ? label(c, `finance:methods.${text(c.data.method)}`, text(c.data.method)) : undefined,
  }),
  rate_out_of_bounds: (c) => ({
    roomType: text(c.data.room_type),
    ratePlan: text(c.data.rate_plan),
    count: count(c.data.count),
    first: day(c, c.data.first),
    prices: joinCodes(c, texts(c.data.prices).map((price) => formatMoney(price, c.currency))),
  }),
  unposted_nights: (c) => ({
    code: code(c),
    guest: text(c.data.guest),
    room: c.data.room === undefined ? undefined : text(c.data.room) ? c.t('control:alertText.common.room', { number: text(c.data.room) }) : c.t('control:alertText.common.theirRoom'),
    count: count(c.data.nights),
    first: day(c, texts(c.data.nights)[0]),
  }),
  vip_room_not_ready: (c) => ({
    room: text(c.data.room),
    guest: text(c.data.guest),
    eta: text(c.data.eta),
    roomStatus: text(c.data.room_status) ? label(c, `common:status.room.${text(c.data.room_status)}`, text(c.data.room_status))?.toLocaleLowerCase(c.lang) : undefined,
  }),
  missing_tra: (c) => ({ code: code(c), guest: text(c.data.guest) }),
  missing_invoice: (c) => ({ code: code(c), guest: text(c.data.guest) }),
  cash_difference: (c) => {
    const difference = count(c.data.difference)
    return {
      difference: money(c, c.data.difference, { absolute: true }),
      direction: difference === undefined ? undefined : c.t(difference < 0 ? 'control:alertText.common.shortage' : 'control:alertText.common.surplus'),
      expected: money(c, c.data.expected),
      counted: money(c, c.data.counted),
      user: text(c.data.user),
    }
  },
  oversold: (c) => ({ roomType: text(c.data.room_type), count: count(c.data.count ?? c.data.dates), worst: count(c.data.worst), first: day(c, c.data.first) }),
  daily_brief: (c) => {
    const facts = (c.data.facts ?? {}) as Record<string, unknown>
    return { date: day(c, facts.date) }
  },
  llm_degraded: (c) => ({
    provider: text(c.data.provider_label) ?? (text(c.data.provider) ? label(c, `control:alertText.common.providers.${text(c.data.provider)}`, text(c.data.provider)) : undefined),
    error: errorText(c.data.error),
  }),
  chatbot_handoff: () => ({}),
  // --- bookings, front desk
  inventory_drift: (c) => ({ count: count(c.data.updated) }),
  payment_after_cancellation: (c) => ({ code: code(c), credit: money(c, c.data.credit), amount: money(c, c.data.amount) }),
  overbooking: (c) => ({ code: code(c), count: count(c.data.shortfalls) }),
  unassigned_arrivals: (c) => ({ count: count(c.data.reservations), codes: joinCodes(c, texts(c.data.reservations)) }),
  overdue_departures: (c) => ({ count: count(c.data.reservations), codes: joinCodes(c, texts(c.data.reservations)) }),
  night_audit_errors: (c) => ({ count: count(c.data.errors), date: shortDay(c, c.data.business_date) }),
  // --- legal
  sire_missing_data: (c) => ({ count: count(c.data.count) }),
  sire_unsubmitted: (c) => ({ count: count(c.data.count) }),
  tra_missing_data: (c) => ({ count: count(c.data.count) }),
  tra_error: (c) => ({ count: count(c.data.count) }),
  invoice_resolution: (c) => ({
    variant: text(c.data.code) ? 'blocked' : text(c.data.prefix) ? 'warning' : undefined,
    prefix: text(c.data.prefix),
  }),
  invoice_rejected: (c) => ({ number: text(c.data.number), document: text(c.data.document) }),
  invoice_error: (c) => ({ number: text(c.data.number), document: text(c.data.document) }),
  // --- finance, corporate
  payment_on_closed_folio: () => ({}),
  payment_amount_mismatch: (c) => ({ expected: money(c, c.data.expected), paid: money(c, c.data.paid) }),
  refund_pending: (c) => ({ amount: money(c, c.data.amount) }),
  refund_failed: (c) => ({ amount: money(c, c.data.amount) }),
  payment_voided_by_provider: (c) => ({ reference: text(c.data.reference) }),
  company_over_credit: (c) => ({ company: text(c.data.company), used: money(c, c.data.used), limit: money(c, c.data.limit) }),
  // --- subscription
  plan_limit: (c) => ({ plan: i18nText(c.data.plan_name, c.lang) }),
  // --- system
  automation_failed: (c) => {
    const name = text(c.data[`name_${c.lang}`]) ?? text(c.data.name_es)
    // `task`: the automation's name when the alert has it, else its code (better than a title in another language)
    return { name, task: name ?? text(c.data.code) }
  },
  integration_fallback: (c) => ({
    kindLabel: kindLabel(c, c.data.kind),
    mode: text(c.data.mode) ? label(c, `control:integrations.mode.${text(c.data.mode)}`, text(c.data.mode)) : undefined,
  }),
  // --- channels
  ical_import_failed: (c) => ({ connection: text(c.data.connection), error: errorText(c.data.error) }),
  channel_import_failed: (c) => ({ connection: text(c.data.connection), externalId: text(c.data.external_id), error: errorText(c.data.error) }),
  channel_pull_failed: (c) => ({ connection: text(c.data.connection), error: errorText(c.data.error) }),
  channel_sync_failed: (c) => ({ connection: text(c.data.connection), attempts: count(c.data.attempts), error: errorText(c.data.error) }),
  // --- guest portal
  guestportal_duplicate_guest: (c) => ({ code: code(c), owner: text(c.data.owner) }),
  guestportal_cancelled: (c) => ({ code: code(c), fee: money(c, c.data.fee), credit: money(c, c.data.credit) }),
  guestportal_modified: (c) => ({ code: code(c), checkin: shortDay(c, c.data.checkin), checkout: shortDay(c, c.data.checkout), credit: money(c, c.data.credit) }),
  guestportal_request: (c) => {
    const kind = text(c.data.kind) ?? 'other'
    return {
      code: code(c),
      guest: text(c.data.guest),
      what: i18nText(c.data.extra_name, c.lang) ?? label(c, `control:alertText.guestportal_request.kinds.${kind}`, undefined),
      notes: text(c.data.notes),
      time: text(c.data.time),
    }
  },
}

/** The template `alertText.<key>` filled with `vars`, or null when it does not exist or lacks a value. */
function fill(ctx: Ctx, key: string, vars: Vars): string | null {
  const full = `alertText.${key}`
  const templates = PLURAL_SUFFIXES.map((suffix) => ctx.i18n.getResource(ctx.lang, NS, full + suffix)).filter(
    (value): value is string => typeof value === 'string',
  )
  if (!templates.length) return null
  for (const template of templates) {
    for (const [, name] of template.matchAll(PLACEHOLDER)) {
      const value = vars[name]
      if (value === undefined || value === '') return null
    }
  }
  return ctx.t(full, { ns: NS, ...vars })
}

/** Several optional sentences: the first one is required, the rest are added when they apply and can be filled. */
function sentences(ctx: Ctx, vars: Vars, first: string, rest: [boolean, string][]): string | null {
  const head = fill(ctx, first, vars)
  if (head === null) return null
  const extra = rest.filter(([applies]) => applies).map(([, key]) => fill(ctx, key, vars))
  if (extra.some((item) => item === null)) return null
  return [head, ...extra].join(' ')
}

/** Messages made of parts that depend on the data (the rest use `alertText.<kind>.message`). */
const MESSAGES: Record<string, (ctx: Ctx, vars: Vars) => string | null> = {
  chatbot_handoff: (c) => {
    const name = text(c.data.name)
    const summary = text(c.data.summary)
    const reach = [text(c.data.email), text(c.data.phone)].filter(Boolean).join(' · ')
    const reservation = text(c.data.reservation_code)
    if (c.data.summary === undefined) return null // raised before the summary was stored: keep its text
    const vars: Vars = { name: name ?? c.t('control:alertText.chatbot_handoff.visitor'), summary, reach, code: reservation }
    return sentences(c, vars, c.data.reason === 'low_confidence' ? 'chatbot_handoff.lowConfidence' : 'chatbot_handoff.asked', [
      [Boolean(summary), 'chatbot_handoff.said'],
      [Boolean(reach), 'chatbot_handoff.reach'],
      [!reach, 'chatbot_handoff.noReach'],
      [Boolean(reservation), 'chatbot_handoff.reservation'],
    ])
  },
  daily_brief: (c) => {
    // The brief is written by the AI in Spanish: other languages get the day's figures from its facts.
    if (c.lang === 'es') return null
    const facts = (c.data.facts ?? {}) as Record<string, unknown>
    const alerts = (facts.open_alerts ?? {}) as Record<string, unknown>
    const arrivals = count(facts.arrivals)
    const departures = count(facts.departures)
    const inHouse = count(facts.in_house)
    if (arrivals === undefined || departures === undefined || inHouse === undefined) return null
    const some = (value: unknown) => (count(value) ?? 0) > 0
    const part = (key: string, value: unknown, vars: Vars = {}) => fill(c, `daily_brief.${key}`, { count: count(value), ...vars })
    const parts = [
      [part('arrivals', arrivals), some(facts.arrivals_vip) ? part('vip', facts.arrivals_vip) : '', some(facts.arrivals_unassigned) ? part('unassigned', facts.arrivals_unassigned) : ''],
      [part('departures', departures), some(facts.departures_with_balance) ? part('withBalance', facts.departures_with_balance) : ''],
      [part('inHouse', inHouse, { occupancy: count(facts.occupancy_pct), sold: count(facts.units_sold), total: count(facts.units_total) })],
      some(alerts.critical) || some(alerts.warning) ? [part('alerts', undefined, { critical: count(alerts.critical) ?? 0, warning: count(alerts.warning) ?? 0 })] : [],
    ]
    if (parts.flat().some((item) => item === null)) return null
    // arrivals and departures are built from pieces: their sentence ends here
    return parts
      .map((line, index) => (line.length ? line.join('') + (index < 2 ? '.' : '') : ''))
      .filter(Boolean)
      .join('\n')
  },
  guestportal_duplicate_guest: (c, vars) =>
    c.data.variant === 'companion' || c.data.variant === 'profile' ? fill(c, `guestportal_duplicate_guest.${c.data.variant}`, vars) : null,
  guestportal_cancelled: (c, vars) =>
    sentences(c, vars, (count(c.data.fee) ?? 0) > 0 ? 'guestportal_cancelled.message' : 'guestportal_cancelled.messageNoFee', [
      [(count(c.data.credit) ?? 0) > 0, 'guestportal_cancelled.credit'],
    ]),
  guestportal_modified: (c, vars) => sentences(c, vars, 'guestportal_modified.message', [[(count(c.data.credit) ?? 0) > 0, 'guestportal_modified.credit']]),
  invoice_resolution: (c, vars) => {
    // The blocking variant keeps the numbering error as stored; the warning says what runs out and when.
    if (vars.variant !== 'warning') return null
    const reasons: (string | null)[] = []
    if (c.data.running_out === true) {
      reasons.push(fill(c, 'invoice_resolution.runningOut', { count: count(c.data.remaining), total: count(c.data.total) }))
    }
    if (c.data.expiring === true) {
      const days = count(c.data.days_left)
      const date = text(c.data.valid_to) ? formatDate(String(c.data.valid_to), 'dd/MM/yyyy', c.lang) : undefined
      reasons.push(days !== undefined && days < 0 ? fill(c, 'invoice_resolution.expired', { date }) : fill(c, 'invoice_resolution.expiring', { count: days, date }))
    }
    if (!reasons.length || reasons.some((item) => item === null)) return null
    return fill(c, 'invoice_resolution.warningMessage', { reasons: joinCodes(c, reasons as string[]) })
  },
  plan_limit: (c) => {
    const part = (key: string, value: unknown, unlimited: string) => {
      if (value === null) return fill(c, `plan_limit.${unlimited}`, {})
      const number = count(value)
      return number === undefined ? null : fill(c, `plan_limit.${key}`, { count: number })
    }
    const units = part('units', c.data.units, 'unlimitedUnits')
    const properties = part('properties', c.data.properties, 'unlimitedProperties')
    const maxUnits = part('units', c.data.max_units, 'unlimitedUnits')
    const maxProperties = part('properties', c.data.max_properties, 'unlimitedProperties')
    if ([units, properties, maxUnits, maxProperties].some((item) => item === null)) return null // raised before P-INT
    return fill(c, 'plan_limit.message', { units: units!, properties: properties!, maxUnits: maxUnits!, maxProperties: maxProperties! })
  },
  guestportal_request: (c, vars) => {
    if (c.data.guest === undefined) return null // raised before the request details were stored
    return sentences(c, vars, 'guestportal_request.message', [
      [Boolean(vars.time), 'guestportal_request.time'],
      [Boolean(vars.notes), 'guestportal_request.notes'],
    ])
  },
}

/** Titles that depend on the data (the rest use `alertText.<kind>.title`). */
const TITLES: Record<string, (ctx: Ctx, vars: Vars) => string | null> = {
  guestportal_request: (c, vars) => fill(c, `guestportal_request.titles.${text(c.data.kind) ?? 'other'}`, vars),
  invoice_resolution: (c, vars) =>
    vars.variant === 'blocked'
      ? fill(c, 'invoice_resolution.blockedTitle', vars)
      : vars.variant === 'warning'
        ? fill(c, 'invoice_resolution.warningTitle', vars)
        : null,
  invoice_rejected: (c, vars) => (vars.document ? fill(c, `invoice_rejected.titles.${vars.document}`, vars) : null),
  invoice_error: (c, vars) => (vars.document ? fill(c, `invoice_error.titles.${vars.document}`, vars) : null),
}

/** Title and message of `alert` in the viewer's language (the stored text when there is no translation). */
export function alertText(alert: Alert, t: TFunction, i18n: I18n, lang: Lang, currency = 'COP'): AlertText {
  const ctx: Ctx = { alert, data: alert.data ?? {}, t, i18n, lang, currency }
  const variables = VARIABLES[alert.kind]
  if (!variables) return { title: alert.title, message: alert.message }
  let vars: Vars
  try {
    vars = variables(ctx)
  } catch {
    return { title: alert.title, message: alert.message }
  }
  const title = TITLES[alert.kind] ? TITLES[alert.kind](ctx, vars) : fill(ctx, `${alert.kind}.title`, vars)
  const message = MESSAGES[alert.kind] ? MESSAGES[alert.kind](ctx, vars) : fill(ctx, `${alert.kind}.message`, vars)
  return { title: title ?? alert.title, message: message ?? alert.message }
}

/** `alertText` bound to the viewer's language and the hotel's currency (for the bell, the widget and the list). */
export function useAlertText(): (alert: Alert) => AlertText {
  const { t, i18n } = useTranslation('control')
  const { property } = useActiveProperty()
  const lang = normalizeLang(i18n.language)
  const currency = property?.currency ?? 'COP'
  return useCallback((alert: Alert) => alertText(alert, t, i18n, lang, currency), [t, i18n, lang, currency])
}
