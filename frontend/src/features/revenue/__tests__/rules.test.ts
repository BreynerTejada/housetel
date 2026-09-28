import { describe, expect, it } from 'vitest'
import type { PricingRule } from '../api'
import { draftFromRule, draftToInput, newRuleDraft, type RuleDraft } from '../lib/rules'

function draft(overrides: Partial<RuleDraft> = {}): RuleDraft {
  return { ...newRuleDraft('occupancy', '2026-10-01'), name: 'Ocupación', ...overrides }
}

describe('draftToInput', () => {
  it('turns occupancy tiers typed in any order into sorted numeric params', () => {
    const value = draft()
    value.params.occupancy.tiers = [
      { min: '85', max: '100', adjust: '15' },
      { min: '0', max: '40', adjust: '-8' },
      { min: '70', max: '85', adjust: '7,5' },
    ]
    const result = draftToInput(value)
    expect(result.errors).toEqual({})
    expect(result.input).toEqual({
      name: 'Ocupación',
      kind: 'occupancy',
      room_types: [],
      combine: 'stack',
      priority: 10,
      is_active: true,
      params: {
        tiers: [
          { min: 0, max: 40, adjust: -8 },
          { min: 70, max: 85, adjust: 7.5 },
          { min: 85, max: 100, adjust: 15 },
        ],
      },
    })
  })

  it('points at the tier that overlaps another or runs backwards', () => {
    const value = draft()
    value.params.occupancy.tiers = [
      { min: '0', max: '50', adjust: '-8' },
      { min: '40', max: '80', adjust: '5' },
      { min: '90', max: '85', adjust: '5' },
    ]
    expect(draftToInput(value).errors).toEqual({
      'tiers.1.min': 'errors.tierOverlap',
      'tiers.2.max': 'errors.tierRange',
    })
  })

  it('checks every adjustment is a number between −90 % and +300 %', () => {
    const value = draft()
    value.params.occupancy.tiers = [
      { min: '0', max: '40', adjust: '' },
      { min: '40', max: '60', adjust: '-95' },
    ]
    expect(draftToInput(value).errors).toEqual({
      'tiers.0.adjust': 'errors.number',
      'tiers.1.adjust': 'errors.adjustRange',
    })
  })

  it('maps last-minute and early-bird windows to their day limits', () => {
    const value = draft({ kind: 'lead_time', name: 'Anticipación' })
    value.params.lead_time = {
      last_minute: [{ days: '3', adjust: '-5' }],
      early_bird: [{ days: '60', adjust: '4' }],
    }
    expect(draftToInput(value).input?.params).toEqual({
      last_minute: [{ max_days: 3, adjust: -5 }],
      early_bird: [{ min_days: 60, adjust: 4 }],
    })
    value.params.lead_time.early_bird = [{ days: '2', adjust: '4' }]
    expect(draftToInput(value).errors).toEqual({ 'early_bird.0.days': 'errors.earlyAfterLastMinute' })
    value.params.lead_time = { last_minute: [], early_bird: [] }
    expect(draftToInput(value).errors).toEqual({ params: 'errors.needOneWindow' })
  })

  it('sends only the weekdays that were filled in', () => {
    const value = draft({ kind: 'day_of_week', name: 'Fin de semana' })
    value.params.day_of_week = { mon: '', tue: '', wed: '', thu: '', fri: '5', sat: '10', sun: '' }
    expect(draftToInput(value).input?.params).toEqual({ fri: 5, sat: 10 })
    value.params.day_of_week = { mon: '', tue: '', wed: '', thu: '', fri: '', sat: '', sun: '' }
    expect(draftToInput(value).errors).toEqual({ params: 'errors.needOneDay' })
  })

  it('keeps an event with its inclusive nights and asks for dates in order', () => {
    const value = draft({ kind: 'event', name: 'Festival' })
    value.params.event = { name: 'Festival de Música', start: '2027-01-07', end: '2027-01-12', adjust: '20' }
    expect(draftToInput(value).input?.params).toEqual({
      name: 'Festival de Música',
      start: '2027-01-07',
      end: '2027-01-12',
      adjust: 20,
    })
    value.params.event = { ...value.params.event, end: '2027-01-01' }
    expect(draftToInput(value).errors).toEqual({ 'event.end': 'errors.eventDates' })
  })

  it('limits the rule to the chosen categories only when "all" is off, and needs a name', () => {
    const value = draft({ kind: 'holiday', allRoomTypes: false, room_types: ['rt-ste'], combine: 'max', priority: '30' })
    value.params.holiday = { adjust: '12', include_bridges: false }
    expect(draftToInput(value).input).toMatchObject({
      room_types: ['rt-ste'],
      combine: 'max',
      priority: 30,
      params: { adjust: 12, include_bridges: false },
    })
    expect(draftToInput({ ...value, allRoomTypes: false, room_types: [] }).errors).toEqual({
      room_types: 'errors.needRoomType',
    })
    expect(draftToInput({ ...value, name: '  ' }).errors).toEqual({ name: 'errors.name' })
  })
})

describe('draftFromRule', () => {
  it('fills the editor with a saved rule so saving it again sends the same params', () => {
    const rule: PricingRule<'lead_time'> = {
      id: 'rule-1',
      name: 'Última hora',
      kind: 'lead_time',
      room_types: ['rt-dbl'],
      params: { last_minute: [{ max_days: 3, adjust: -5 }], early_bird: [] },
      priority: 15,
      combine: 'stack',
      is_active: false,
      created_at: '',
      updated_at: '',
    }
    const value = draftFromRule(rule, '2026-10-01')
    expect(value.params.lead_time.last_minute).toEqual([{ days: '3', adjust: '-5' }])
    expect(value.allRoomTypes).toBe(false)
    expect(draftToInput(value).input).toEqual({
      name: 'Última hora',
      kind: 'lead_time',
      room_types: ['rt-dbl'],
      combine: 'stack',
      priority: 15,
      is_active: false,
      params: { last_minute: [{ max_days: 3, adjust: -5 }], early_bird: [] },
    })
  })
})
