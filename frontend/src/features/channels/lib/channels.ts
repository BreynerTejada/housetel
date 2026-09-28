/**
 * Pure helpers of the channel manager: prices as the channel sells them, connection health per direction,
 * the wizard's draft (suggested mappings) and the payload it sends, and what an OTA grid cell means.
 */
import type {
  ChannelCode,
  ChannelOptions,
  Connection,
  ConnectionInput,
  IntegrationMode,
  OtaCell,
} from '../api'

// ---- money --------------------------------------------------------------------------------------------------

interface Decimal {
  units: bigint
  scale: number
}

function parseDecimal(value: string | number): Decimal | null {
  const text = String(value ?? '').trim()
  if (!/^-?\d+(\.\d+)?$/.test(text)) return null
  const negative = text.startsWith('-')
  const [whole, fraction = ''] = text.replace('-', '').split('.')
  const units = BigInt(whole + fraction)
  return { units: negative ? -units : units, scale: fraction.length }
}

/** a / b rounded half up (away from zero on .5), b > 0. */
function divideHalfUp(a: bigint, b: bigint): bigint {
  const negative = a < 0n
  const magnitude = negative ? -a : a
  const rounded = (2n * magnitude + b) / (2n * b)
  return negative ? -rounded : rounded
}

const TEN = 10n

function pow10(exponent: number): bigint {
  return TEN ** BigInt(exponent)
}

function formatUnits(units: bigint, digits: number): string {
  const negative = units < 0n
  const text = (negative ? -units : units).toString().padStart(digits + 1, '0')
  const whole = digits ? text.slice(0, -digits) : text
  const fraction = digits ? text.slice(-digits) : ''
  return `${negative ? '-' : ''}${whole}.${fraction.padEnd(2, '0')}`
}

/**
 * The nightly price a channel receives for a plan price and a markup, exactly as the backend computes it
 * (`services.ari.channel_price`): plan price rounded to the currency, × (1 + markup/100), rounded again.
 * COP rounds to whole pesos, other currencies to cents, always half up. Returns "368000.00".
 */
export function channelPrice(price: string | number, markupPercent: string | number, currency = 'COP'): string {
  const digits = currency === 'COP' ? 0 : 2
  const parsedPrice = parseDecimal(price) ?? { units: 0n, scale: 0 }
  const markup = parseDecimal(markupPercent === '' ? '0' : markupPercent) ?? { units: 0n, scale: 0 }
  const planUnits = divideHalfUp(parsedPrice.units * pow10(digits), pow10(parsedPrice.scale))
  const factorScale = pow10(markup.scale)
  const numerator = planUnits * (100n * factorScale + markup.units)
  return formatUnits(divideHalfUp(numerator, 100n * factorScale), digits)
}

// ---- channels -----------------------------------------------------------------------------------------------

const PREFIXES: Record<ChannelCode, string> = { booksim: 'BS', airsim: 'AS', channex: 'CX', ical: '' }
const DEFAULT_MARKUP: Record<ChannelCode, string> = { booksim: '15', airsim: '12', channex: '0', ical: '0' }
const DEFAULT_NAMES: Record<ChannelCode, string> = { booksim: 'BookSim', airsim: 'AirSim', channex: 'Channex', ical: 'Airbnb' }

/** Readable channel ids for simulated channels (`BS-DBL`, `AS-FLEX`); iCal needs none. */
export function suggestedExternalId(channel: ChannelCode, code: string): string {
  const prefix = PREFIXES[channel]
  return prefix ? `${prefix}-${code}` : ''
}

export type LaneHealth = 'ok' | 'queued' | 'error' | 'paused' | 'idle'

/**
 * Health of one direction of a connection. `out`: what Housetel sends (ARI; for iCal, the exported
 * calendars). `in`: what arrives (bookings, imported calendars).
 */
export function laneHealth(connection: Connection, lane: 'out' | 'in'): LaneHealth {
  if (connection.status === 'paused') return 'paused'
  const stats = connection.stats
  if (lane === 'out') {
    if (connection.channel_code === 'ical') return connection.room_mappings.length ? 'ok' : 'idle'
    if (stats.failed_updates > 0 || connection.status === 'error') return 'error'
    if (stats.pending_updates > 0) return 'queued'
    return stats.last_out_at ? 'ok' : 'idle'
  }
  if (stats.in_errors_24h > 0) return 'error'
  return stats.last_in_at ? 'ok' : 'idle'
}

// ---- wizard draft -------------------------------------------------------------------------------------------

export interface RoomDraft {
  id?: string
  roomTypeId: string
  /** iCal only: a calendar for one room instead of the category. */
  roomId: string | null
  enabled: boolean
  externalId: string
  importUrl: string
}

export interface RateDraft {
  id?: string
  planId: string
  /** Set when the channel rate belongs to one room (Channex). */
  roomTypeId: string | null
  enabled: boolean
  externalId: string
  markup: string
}

export interface ConnectionDraft {
  channel: ChannelCode
  name: string
  /** null = keep the integration mode as it is. */
  mode: IntegrationMode | null
  config: Record<string, string>
  initialConfig: Record<string, string>
  secrets: Record<string, string>
  rooms: RoomDraft[]
  rates: RateDraft[]
  importAll: boolean
  fullSync: boolean
}

function sellsOn(plan: ChannelOptions['rate_plans'][number], channel: ChannelCode): boolean {
  return plan.is_active && plan.is_public && (plan.channels.length === 0 || plan.channels.includes(channel))
}

/** The wizard's starting point: every active category mapped with a suggested id and the plans the channel
 * may sell (public, open to OTAs) checked; or the current mappings of `existing` first when editing. */
export function initialDraft(channel: ChannelCode, options: ChannelOptions, existing?: Connection): ConnectionDraft {
  const activeTypes = options.room_types.filter((roomType) => roomType.is_active)
  const typeCode = new Map(options.room_types.map((roomType) => [roomType.id, roomType.code]))
  const integrationKind = channel === 'ical' ? 'channel_ical' : channel === 'channex' ? 'channel_channex' : null
  const config = { ...(existing?.integration?.config ?? (integrationKind ? options.integrations[integrationKind]?.config : {}) ?? {}) }

  const rooms: RoomDraft[] = []
  for (const mapping of existing?.room_mappings ?? []) {
    rooms.push({
      id: mapping.id,
      roomTypeId: mapping.room_type,
      roomId: mapping.room,
      enabled: true,
      externalId: mapping.external_room_id,
      importUrl: mapping.ical_import_url,
    })
  }
  const mappedTypes = new Set(rooms.filter((room) => !room.roomId).map((room) => room.roomTypeId))
  for (const roomType of activeTypes) {
    if (mappedTypes.has(roomType.id)) continue
    rooms.push({
      roomTypeId: roomType.id,
      roomId: null,
      enabled: !existing,
      externalId: suggestedExternalId(channel, roomType.code),
      importUrl: '',
    })
  }

  const rates: RateDraft[] = []
  if (channel !== 'ical') {
    for (const mapping of existing?.rate_mappings ?? []) {
      if (!mapping.rate_plan) continue // its plan was deleted: saving drops the mapping
      rates.push({
        id: mapping.id,
        planId: mapping.rate_plan,
        roomTypeId: mapping.room_type,
        enabled: true,
        externalId: mapping.external_rate_id,
        markup: mapping.markup_percent,
      })
    }
    const mapped = new Set(rates.map((rate) => `${rate.planId}:${rate.roomTypeId ?? ''}`))
    for (const plan of options.rate_plans.filter((item) => item.is_active)) {
      const perRoom = channel === 'channex' ? plan.room_types : [null]
      for (const roomTypeId of perRoom) {
        if (mapped.has(`${plan.id}:${roomTypeId ?? ''}`)) continue
        const code = roomTypeId ? `${plan.code}-${typeCode.get(roomTypeId) ?? ''}` : plan.code
        rates.push({
          planId: plan.id,
          roomTypeId,
          enabled: !existing && sellsOn(plan, channel),
          externalId: suggestedExternalId(channel, code),
          markup: DEFAULT_MARKUP[channel],
        })
      }
    }
  }

  return {
    channel,
    name: existing?.name ?? DEFAULT_NAMES[channel],
    mode: null,
    config,
    initialConfig: { ...config },
    secrets: {},
    rooms,
    rates,
    importAll: Boolean(existing?.settings.import_all_events),
    fullSync: channel !== 'ical',
  }
}

/** What the wizard sends to `POST/PATCH connections/`: only the checked mappings, trimmed. */
export function buildConnectionInput(draft: ConnectionDraft, { editing = false } = {}): ConnectionInput {
  const input: ConnectionInput = {}
  if (!editing) input.channel_code = draft.channel
  input.name = draft.name.trim()
  if (draft.channel === 'ical') input.settings = { import_all_events: draft.importAll }
  input.room_mappings = draft.rooms
    .filter((room) => room.enabled)
    .map((room) => ({
      ...(room.id ? { id: room.id } : {}),
      room_type: room.roomTypeId,
      room: room.roomId,
      external_room_id: room.externalId.trim(),
      ical_import_url: room.importUrl.trim(),
    }))
  if (draft.channel !== 'ical') {
    input.rate_mappings = draft.rates
      .filter((rate) => rate.enabled)
      .map((rate) => ({
        ...(rate.id ? { id: rate.id } : {}),
        rate_plan: rate.planId,
        room_type: rate.roomTypeId,
        external_rate_id: rate.externalId.trim(),
        markup_percent: rate.markup.trim() || '0',
      }))
  }
  const hasIntegration = draft.channel === 'ical' || draft.channel === 'channex'
  if (hasIntegration && draft.mode) input.mode = draft.mode
  if (hasIntegration) {
    const config = Object.fromEntries(
      Object.entries(draft.config).filter(([key, value]) => value.trim() && value !== draft.initialConfig[key]),
    )
    const secrets = Object.fromEntries(Object.entries(draft.secrets).filter(([, value]) => value.trim()))
    if (Object.keys(config).length || Object.keys(secrets).length) {
      input.integration = {
        ...(Object.keys(config).length ? { config } : {}),
        ...(Object.keys(secrets).length ? { secrets } : {}),
      }
    }
  }
  if (draft.channel !== 'ical' && draft.fullSync) input.full_sync = true
  return input
}

/** Why the wizard cannot move on from the mapping step (i18n keys of `wizard.problems.*`), or []. */
export function mappingProblems(draft: ConnectionDraft): string[] {
  const problems: string[] = []
  const rooms = draft.rooms.filter((room) => room.enabled)
  if (!rooms.length) problems.push('noRooms')
  if (draft.channel !== 'ical') {
    if (rooms.some((room) => !room.externalId.trim())) problems.push('roomCode')
    const codes = rooms.map((room) => room.externalId.trim()).filter(Boolean)
    if (new Set(codes).size !== codes.length) problems.push('roomDuplicate')
    const rates = draft.rates.filter((rate) => rate.enabled)
    if (rates.some((rate) => !rate.externalId.trim())) problems.push('rateCode')
    const rateCodes = rates.map((rate) => rate.externalId.trim()).filter(Boolean)
    if (new Set(rateCodes).size !== rateCodes.length) problems.push('rateDuplicate')
    if (rates.some((rate) => !isValidMarkup(rate.markup))) problems.push('markup')
  } else if (rooms.some((room) => room.importUrl.trim() && !/^(https?|webcal):\/\/\S+$/i.test(room.importUrl.trim()))) {
    problems.push('url')
  }
  return problems
}

/** A markup the backend accepts: a number from −90 to 300 (empty = 0). */
export function isValidMarkup(value: string): boolean {
  const text = value.trim().replace(',', '.')
  if (!text) return true
  if (!/^-?\d+(\.\d{1,2})?$/.test(text)) return false
  const number = Number(text)
  return number >= -90 && number <= 300
}

/** The plan is sold on the channel (public, active, open to that channel); otherwise the channel gets it closed. */
export function planSellsOn(plan: ChannelOptions['rate_plans'][number], channel: ChannelCode): boolean {
  return sellsOn(plan, channel)
}

// ---- dates --------------------------------------------------------------------------------------------------

/** `YYYY-MM-DD` + n days (calendar days, no time zone surprises). */
export function addDaysISO(value: string, days: number): string {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}

/** The nights of `[checkin, checkout)` as `YYYY-MM-DD`. */
export function nightsOf(checkin: string, checkout: string): string[] {
  const nights: string[] = []
  for (let day = checkin; day < checkout; day = addDaysISO(day, 1)) nights.push(day)
  return nights
}

// ---- OTA quote (what the simulated OTA would charge, from the ARI it holds) -------------------------------------

export type OtaProblem =
  | { code: 'missing'; date: string }
  | { code: 'closed'; date: string }
  | { code: 'soldOut'; date: string; available: number }
  | { code: 'cta'; date: string }
  | { code: 'ctd'; date: string }
  | { code: 'minLos'; nights: number }
  | { code: 'maxLos'; nights: number }

export interface OtaQuote {
  nights: { date: string; price: string | null; state: CellState }[]
  /** Σ price × units when every night has a price; null otherwise. */
  total: string | null
  problems: OtaProblem[]
}

/**
 * What the OTA would say about a stay, from the cells it holds (`cells[date]`, the checkout day included for
 * closed-to-departure). Mirrors the checks of the backend simulator; `units` = beds in a dorm, else 1.
 */
export function otaQuote(cells: Record<string, OtaCell | null | undefined>, checkin: string, checkout: string, units: number): OtaQuote {
  const nights = nightsOf(checkin, checkout)
  const problems: OtaProblem[] = []
  let total = 0
  let priced = true
  const rows = nights.map((date) => {
    const cell = cells[date] ?? null
    const state = cellState(cell)
    if (!cell) problems.push({ code: 'missing', date })
    else if (cell.stop_sell || cell.price === null) problems.push({ code: 'closed', date })
    if (cell && cell.available < units) problems.push({ code: 'soldOut', date, available: Math.max(cell.available, 0) })
    if (cell?.price != null) total += Number(cell.price) * units
    else priced = false
    return { date, price: cell?.price ?? null, state }
  })
  const arrival = cells[checkin]
  if (arrival) {
    if (arrival.closed_to_arrival) problems.push({ code: 'cta', date: checkin })
    if (arrival.min_los && nights.length < arrival.min_los) problems.push({ code: 'minLos', nights: arrival.min_los })
    if (arrival.max_los && nights.length > arrival.max_los) problems.push({ code: 'maxLos', nights: arrival.max_los })
  }
  if (cells[checkout]?.closed_to_departure) problems.push({ code: 'ctd', date: checkout })
  return { nights: rows, total: priced && nights.length ? total.toFixed(2) : null, problems }
}

/** Signature of a cell, to spot the ones a new ARI push changed. */
export function cellSignature(cell: OtaCell | null): string {
  if (!cell) return '-'
  return [cell.available, cell.price, cell.min_los, cell.max_los, cell.closed_to_arrival, cell.closed_to_departure, cell.stop_sell].join('|')
}

// ---- OTA grid -----------------------------------------------------------------------------------------------

export type CellState = 'open' | 'soldout' | 'closed' | 'missing'

/** What a guest of the OTA could do on that night. */
export function cellState(cell: OtaCell | null): CellState {
  if (!cell) return 'missing'
  if (cell.stop_sell || cell.price === null) return 'closed'
  if (cell.available <= 0) return 'soldout'
  return 'open'
}
