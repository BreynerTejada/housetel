import type {
  Combine,
  DayOfWeekParams,
  EventParams,
  HolidayParams,
  LeadTimeParams,
  OccupancyParams,
  PricingRule,
  RuleInput,
  RuleKind,
  Weekday,
} from '../api'
import { addDays } from './dates'

/**
 * The rule editor works on drafts: what people type (strings), for every kind at once, so switching the kind
 * of a new rule never loses what was typed. `draftToInput` checks the draft like the API does (same limits:
 * adjustments −90 %…+300 %, occupancy 0–100 % without overlaps, whole days up to 730, events up to a year)
 * and returns the payload or the errors by field path, each an i18n key of the `revenue` namespace.
 */

export const RULE_KINDS: RuleKind[] = ['occupancy', 'lead_time', 'day_of_week', 'holiday', 'event']
export const WEEKDAYS: Weekday[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

const MIN_ADJUST = -90
const MAX_ADJUST = 300
const MAX_DAYS = 730
const MAX_EVENT_NIGHTS = 366
const MAX_PRIORITY = 32767

export interface TierDraft {
  min: string
  max: string
  adjust: string
}

export interface WindowDraft {
  days: string
  adjust: string
}

export interface ParamsDraft {
  occupancy: { tiers: TierDraft[] }
  lead_time: { last_minute: WindowDraft[]; early_bird: WindowDraft[] }
  day_of_week: Record<Weekday, string>
  holiday: { adjust: string; include_bridges: boolean }
  event: { name: string; start: string; end: string; adjust: string }
}

export interface RuleDraft {
  id?: string
  name: string
  kind: RuleKind
  /** True = every category (sent as an empty list). */
  allRoomTypes: boolean
  room_types: string[]
  combine: Combine
  priority: string
  is_active: boolean
  params: ParamsDraft
}

export type DraftErrors = Record<string, string>

export function newRuleDraft(kind: RuleKind, today: string): RuleDraft {
  return {
    name: '',
    kind,
    allRoomTypes: true,
    room_types: [],
    combine: 'stack',
    priority: '10',
    is_active: true,
    params: {
      occupancy: {
        tiers: [
          { min: '0', max: '40', adjust: '-8' },
          { min: '70', max: '85', adjust: '8' },
          { min: '85', max: '100', adjust: '15' },
        ],
      },
      lead_time: { last_minute: [{ days: '3', adjust: '-5' }], early_bird: [] },
      day_of_week: { mon: '', tue: '', wed: '', thu: '', fri: '', sat: '8', sun: '' },
      holiday: { adjust: '12', include_bridges: true },
      event: { name: '', start: addDays(today, 30), end: addDays(today, 32), adjust: '15' },
    },
  }
}

const text = (value: number | undefined) => (value === undefined || value === null ? '' : String(value))

export function draftFromRule(rule: PricingRule, today: string): RuleDraft {
  const draft = newRuleDraft(rule.kind, today)
  const params = rule.params
  switch (rule.kind) {
    case 'occupancy':
      draft.params.occupancy = {
        tiers: (params as OccupancyParams).tiers.map((tier) => ({
          min: text(tier.min),
          max: text(tier.max),
          adjust: text(tier.adjust),
        })),
      }
      break
    case 'lead_time': {
      const lead = params as LeadTimeParams
      draft.params.lead_time = {
        last_minute: lead.last_minute.map((item) => ({ days: text(item.max_days), adjust: text(item.adjust) })),
        early_bird: lead.early_bird.map((item) => ({ days: text(item.min_days), adjust: text(item.adjust) })),
      }
      break
    }
    case 'day_of_week': {
      const days = params as DayOfWeekParams
      draft.params.day_of_week = Object.fromEntries(WEEKDAYS.map((day) => [day, text(days[day])])) as Record<Weekday, string>
      break
    }
    case 'holiday': {
      const holiday = params as HolidayParams
      draft.params.holiday = { adjust: text(holiday.adjust), include_bridges: holiday.include_bridges }
      break
    }
    case 'event': {
      const event = params as EventParams
      draft.params.event = { name: event.name ?? '', start: event.start, end: event.end, adjust: text(event.adjust) }
      break
    }
  }
  return {
    ...draft,
    id: rule.id,
    name: rule.name,
    allRoomTypes: rule.room_types.length === 0,
    room_types: rule.room_types,
    combine: rule.combine,
    priority: String(rule.priority),
    is_active: rule.is_active,
  }
}

/** "7,5", "7.5", "+8", "−8" → number; `null` when it is not a number. */
export function parseNumber(value: string): number | null {
  const cleaned = value.trim().replace('−', '-').replace(',', '.').replace(/^\+/, '')
  if (!cleaned || !/^-?\d+(\.\d+)?$/.test(cleaned)) return null
  return Number(cleaned)
}

function adjustOf(value: string, key: string, errors: DraftErrors): number {
  const number = parseNumber(value)
  if (number === null) errors[key] = 'errors.number'
  else if (number < MIN_ADJUST || number > MAX_ADJUST) errors[key] = 'errors.adjustRange'
  return number ?? 0
}

function daysOf(value: string, key: string, minimum: number, errors: DraftErrors): number {
  const number = parseNumber(value)
  if (number === null || !Number.isInteger(number) || number < minimum || number > MAX_DAYS) errors[key] = 'errors.days'
  return number ?? 0
}

function occupancyParams(draft: ParamsDraft['occupancy'], errors: DraftErrors): OccupancyParams {
  if (draft.tiers.length === 0) errors.params = 'errors.needOneTier'
  const tiers = draft.tiers.map((tier, index) => {
    const min = parseNumber(tier.min)
    const max = parseNumber(tier.max)
    const adjust = adjustOf(tier.adjust, `tiers.${index}.adjust`, errors)
    let valid = true
    if (min === null || min < 0 || min > 100) {
      errors[`tiers.${index}.min`] = 'errors.percentRange'
      valid = false
    }
    if (max === null || max < 0 || max > 100) {
      errors[`tiers.${index}.max`] = 'errors.percentRange'
      valid = false
    } else if (min !== null && min >= max) {
      errors[`tiers.${index}.max`] = 'errors.tierRange'
      valid = false
    }
    return { index, valid, min: min ?? 0, max: max ?? 0, adjust }
  })
  const ordered = tiers.filter((tier) => tier.valid).sort((a, b) => a.min - b.min || a.index - b.index)
  ordered.forEach((tier, position) => {
    const previous = ordered[position - 1]
    if (previous && tier.min < previous.max) errors[`tiers.${tier.index}.min`] = 'errors.tierOverlap'
  })
  return { tiers: [...tiers].sort((a, b) => a.min - b.min).map(({ min, max, adjust }) => ({ min, max, adjust })) }
}

function leadTimeParams(draft: ParamsDraft['lead_time'], errors: DraftErrors): LeadTimeParams {
  if (draft.last_minute.length === 0 && draft.early_bird.length === 0) errors.params = 'errors.needOneWindow'
  const lastMinute = draft.last_minute.map((item, index) => ({
    index,
    max_days: daysOf(item.days, `last_minute.${index}.days`, 0, errors),
    adjust: adjustOf(item.adjust, `last_minute.${index}.adjust`, errors),
  }))
  const earlyBird = draft.early_bird.map((item, index) => ({
    index,
    min_days: daysOf(item.days, `early_bird.${index}.days`, 1, errors),
    adjust: adjustOf(item.adjust, `early_bird.${index}.adjust`, errors),
  }))
  for (const [list, field, prefix] of [
    [lastMinute, 'max_days', 'last_minute'],
    [earlyBird, 'min_days', 'early_bird'],
  ] as const) {
    const seen = new Set<number>()
    for (const item of list as { index: number; [key: string]: number }[]) {
      const days = item[field]
      if (seen.has(days)) errors[`${prefix}.${item.index}.days`] ??= 'errors.duplicateWindow'
      seen.add(days)
    }
  }
  const lastDay = Math.max(...lastMinute.map((item) => item.max_days), -1)
  for (const item of earlyBird) {
    if (item.min_days <= lastDay) errors[`early_bird.${item.index}.days`] ??= 'errors.earlyAfterLastMinute'
  }
  return {
    last_minute: [...lastMinute].sort((a, b) => a.max_days - b.max_days).map(({ max_days, adjust }) => ({ max_days, adjust })),
    early_bird: [...earlyBird].sort((a, b) => a.min_days - b.min_days).map(({ min_days, adjust }) => ({ min_days, adjust })),
  }
}

function dayOfWeekParams(draft: ParamsDraft['day_of_week'], errors: DraftErrors): DayOfWeekParams {
  const params: DayOfWeekParams = {}
  for (const day of WEEKDAYS) {
    if (!draft[day].trim()) continue
    params[day] = adjustOf(draft[day], `days.${day}`, errors)
  }
  if (Object.keys(params).length === 0) errors.params = 'errors.needOneDay'
  return params
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function nightsBetween(start: string, end: string): number {
  const [a, b] = [start, end].map((iso) => {
    const [y, m, d] = iso.split('-').map(Number)
    return Date.UTC(y, m - 1, d)
  })
  return Math.round((b - a) / 86_400_000)
}

function eventParams(draft: ParamsDraft['event'], errors: DraftErrors): EventParams {
  const name = draft.name.trim()
  if (name.length > 120) errors['event.name'] = 'errors.eventName'
  if (!ISO_DATE.test(draft.start)) errors['event.start'] = 'errors.date'
  if (!ISO_DATE.test(draft.end)) errors['event.end'] = 'errors.date'
  else if (ISO_DATE.test(draft.start)) {
    const nights = nightsBetween(draft.start, draft.end)
    if (nights < 0) errors['event.end'] = 'errors.eventDates'
    else if (nights + 1 > MAX_EVENT_NIGHTS) errors['event.end'] = 'errors.eventTooLong'
  }
  return { name, start: draft.start, end: draft.end, adjust: adjustOf(draft.adjust, 'event.adjust', errors) }
}

/** The API payload of a draft, or the errors that keep it from being saved. */
export function draftToInput(draft: RuleDraft): { input: RuleInput | null; errors: DraftErrors } {
  const errors: DraftErrors = {}
  const name = draft.name.trim()
  if (!name) errors.name = 'errors.name'
  const priority = parseNumber(draft.priority)
  if (priority === null || !Number.isInteger(priority) || priority < 0 || priority > MAX_PRIORITY) {
    errors.priority = 'errors.priority'
  }
  if (!draft.allRoomTypes && draft.room_types.length === 0) errors.room_types = 'errors.needRoomType'
  const params =
    draft.kind === 'occupancy'
      ? occupancyParams(draft.params.occupancy, errors)
      : draft.kind === 'lead_time'
        ? leadTimeParams(draft.params.lead_time, errors)
        : draft.kind === 'day_of_week'
          ? dayOfWeekParams(draft.params.day_of_week, errors)
          : draft.kind === 'holiday'
            ? { adjust: adjustOf(draft.params.holiday.adjust, 'holiday.adjust', errors), include_bridges: draft.params.holiday.include_bridges }
            : eventParams(draft.params.event, errors)
  if (Object.keys(errors).length > 0) return { input: null, errors }
  return {
    errors,
    input: {
      name,
      kind: draft.kind,
      room_types: draft.allRoomTypes ? [] : draft.room_types,
      combine: draft.combine,
      priority: priority ?? 10,
      is_active: draft.is_active,
      params,
    },
  }
}
