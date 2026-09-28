import { describe, expect, it } from 'vitest'
import type { ChannelOptions, Connection, OtaCell } from '../api'
import {
  buildConnectionInput,
  cellState,
  channelPrice,
  initialDraft,
  laneHealth,
  suggestedExternalId,
} from '../lib/channels'

const stats = {
  pending_updates: 0,
  failed_updates: 0,
  reservations: 0,
  errors_24h: 0,
  in_errors_24h: 0,
  last_out_at: null,
  last_in_at: null,
}

function connection(overrides: Partial<Connection> = {}): Connection {
  return {
    id: 'c1',
    channel_code: 'booksim',
    channel_label: 'BookSim',
    name: 'BookSim',
    status: 'active',
    mode: 'simulated',
    delivery: 'push',
    simulated: true,
    settings: {},
    last_sync_at: null,
    last_error: '',
    created_at: '2026-09-25T10:00:00-05:00',
    updated_at: '2026-09-25T10:00:00-05:00',
    room_mappings: [],
    rate_mappings: [],
    stats,
    integration: null,
    ...overrides,
  }
}

const OPTIONS: ChannelOptions = {
  channels: [],
  room_types: [
    { id: 'rt-dbl', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, kind: 'private', color: '#4E6C88', is_active: true, rooms: [{ id: 'r-101', number: '101' }] },
    { id: 'rt-old', code: 'OLD', name: { es: 'Antigua' }, kind: 'private', color: '#999999', is_active: false, rooms: [] },
  ],
  rate_plans: [
    { id: 'p-flex', code: 'FLEX', name: { es: 'Flexible' }, kind: 'base', room_types: ['rt-dbl'], is_public: true, is_active: true, channels: [] },
    { id: 'p-corp', code: 'CORP', name: { es: 'Corporativa' }, kind: 'base', room_types: ['rt-dbl'], is_public: false, is_active: true, channels: [] },
    { id: 'p-web', code: 'WEB', name: { es: 'Web' }, kind: 'derived', room_types: ['rt-dbl'], is_public: true, is_active: true, channels: ['direct'] },
  ],
  integrations: {
    channel_ical: { kind: 'channel_ical', mode: 'simulated', enabled: true, config: {}, secrets: [], fields: [] },
    channel_channex: { kind: 'channel_channex', mode: 'simulated', enabled: true, config: {}, secrets: [], fields: [] },
  },
  currency: 'COP',
  business_date: '2026-10-01',
}

describe('channelPrice', () => {
  it('adds the markup and rounds COP to whole pesos like the backend', () => {
    expect(channelPrice('320000.00', '15')).toBe('368000.00')
    expect(channelPrice('650000', '12.5')).toBe('731250.00')
    expect(channelPrice('281600', '15')).toBe('323840.00')
    expect(channelPrice('99999.5', '10')).toBe('110000.00') // the plan price is rounded first
    expect(channelPrice('100001', '0.5')).toBe('100501.00')
  })

  it('keeps cents for other currencies and tolerates an empty markup', () => {
    expect(channelPrice('100.00', '7.5', 'USD')).toBe('107.50')
    expect(channelPrice('320000', '')).toBe('320000.00')
  })
})

describe('suggestedExternalId', () => {
  it('uses a readable prefix per channel', () => {
    expect(suggestedExternalId('booksim', 'DBL')).toBe('BS-DBL')
    expect(suggestedExternalId('airsim', 'FLEX')).toBe('AS-FLEX')
    expect(suggestedExternalId('channex', 'STE')).toBe('CX-STE')
    expect(suggestedExternalId('ical', 'DBL')).toBe('')
  })
})

describe('laneHealth', () => {
  it('reads the outgoing lane from the queue', () => {
    expect(laneHealth(connection(), 'out')).toBe('idle')
    expect(laneHealth(connection({ stats: { ...stats, last_out_at: '2026-09-25T10:00:00-05:00' } }), 'out')).toBe('ok')
    expect(laneHealth(connection({ stats: { ...stats, pending_updates: 2 } }), 'out')).toBe('queued')
    expect(laneHealth(connection({ stats: { ...stats, pending_updates: 2, failed_updates: 1 } }), 'out')).toBe('error')
    expect(laneHealth(connection({ status: 'error' }), 'out')).toBe('error')
  })

  it('reads the incoming lane from the log and pauses both', () => {
    expect(laneHealth(connection({ stats: { ...stats, last_in_at: '2026-09-25T10:00:00-05:00' } }), 'in')).toBe('ok')
    expect(laneHealth(connection({ stats: { ...stats, in_errors_24h: 1 } }), 'in')).toBe('error')
    expect(laneHealth(connection({ status: 'paused', stats: { ...stats, failed_updates: 3 } }), 'out')).toBe('paused')
    expect(laneHealth(connection({ status: 'paused' }), 'in')).toBe('paused')
  })
})

describe('initialDraft', () => {
  it('maps the active categories and the plans the channel may sell, with suggested ids', () => {
    const draft = initialDraft('booksim', OPTIONS)

    expect(draft.rooms).toEqual([{ roomTypeId: 'rt-dbl', roomId: null, enabled: true, externalId: 'BS-DBL', importUrl: '' }])
    // private plans and plans closed to OTAs start unchecked
    expect(draft.rates.map((rate) => [rate.planId, rate.enabled, rate.externalId, rate.markup])).toEqual([
      ['p-flex', true, 'BS-FLEX', '15'],
      ['p-corp', false, 'BS-CORP', '15'],
      ['p-web', false, 'BS-WEB', '15'],
    ])
    expect(draft.fullSync).toBe(true)
  })

  it('starts iCal with one calendar per category and no rates', () => {
    const draft = initialDraft('ical', OPTIONS)

    expect(draft.rooms).toEqual([{ roomTypeId: 'rt-dbl', roomId: null, enabled: true, externalId: '', importUrl: '' }])
    expect(draft.rates).toEqual([])
    expect(draft.name).toBe('Airbnb')
  })

  it('starts from an existing connection when editing', () => {
    const existing = connection({
      room_mappings: [
        { id: 'm1', room_type: 'rt-dbl', room_type_code: 'DBL', room_type_name: 'Estándar', room: null, room_number: null,
          external_room_id: 'BS-DOUBLE', ical_import_url: '', ical_export_url: null, ical_last_sync_at: null, ical_last_error: '' },
      ],
      rate_mappings: [
        { id: 'r1', rate_plan: 'p-flex', rate_plan_code: 'FLEX', rate_plan_name: 'Flexible', room_type: null, room_type_code: null,
          external_rate_id: 'BS-F', markup_percent: '10.00' },
      ],
    })

    const draft = initialDraft('booksim', OPTIONS, existing)

    expect(draft.rooms[0]).toEqual({ id: 'm1', roomTypeId: 'rt-dbl', roomId: null, enabled: true, externalId: 'BS-DOUBLE', importUrl: '' })
    expect(draft.rates[0]).toMatchObject({ id: 'r1', planId: 'p-flex', enabled: true, externalId: 'BS-F', markup: '10.00' })
    expect(draft.rates.find((rate) => rate.planId === 'p-corp')?.enabled).toBe(false)
  })
})

describe('buildConnectionInput', () => {
  it('sends only the enabled mappings, trimmed', () => {
    const draft = initialDraft('booksim', OPTIONS)
    draft.rooms[0].externalId = '  BS-DBL '
    draft.rates[2].enabled = true

    expect(buildConnectionInput(draft)).toEqual({
      channel_code: 'booksim',
      name: 'BookSim',
      room_mappings: [{ room_type: 'rt-dbl', room: null, external_room_id: 'BS-DBL', ical_import_url: '' }],
      rate_mappings: [
        { rate_plan: 'p-flex', room_type: null, external_rate_id: 'BS-FLEX', markup_percent: '15' },
        { rate_plan: 'p-web', room_type: null, external_rate_id: 'BS-WEB', markup_percent: '15' },
      ],
      full_sync: true,
    })
  })

  it('adds the mode and credentials for Channex and the import option for iCal', () => {
    const channex = { ...initialDraft('channex', OPTIONS), mode: 'real' as const, config: { environment: 'staging', property_id: 'p1' }, secrets: { api_key: 'k', unused: '' } }
    expect(buildConnectionInput(channex)).toMatchObject({
      channel_code: 'channex',
      mode: 'real',
      integration: { config: { environment: 'staging', property_id: 'p1' }, secrets: { api_key: 'k' } },
    })

    const ical = { ...initialDraft('ical', OPTIONS), importAll: true }
    ical.rooms[0].importUrl = ' https://www.airbnb.com/calendar/ical/1.ics '
    const input = buildConnectionInput(ical)
    expect(input.settings).toEqual({ import_all_events: true })
    expect(input.rate_mappings).toBeUndefined()
    expect(input.room_mappings?.[0].ical_import_url).toBe('https://www.airbnb.com/calendar/ical/1.ics')
    expect(input.full_sync).toBeUndefined()
  })

  it('omits channel_code, keeps mapping ids and never re-sends stored secrets when editing', () => {
    const existing = connection({ id: 'c9' })
    const draft = { ...initialDraft('booksim', OPTIONS, existing), rooms: [{ id: 'm1', roomTypeId: 'rt-dbl', roomId: null, enabled: true, externalId: 'BS-DBL', importUrl: '' }] }

    const input = buildConnectionInput(draft, { editing: true })

    expect(input.channel_code).toBeUndefined()
    expect(input.room_mappings?.[0].id).toBe('m1')
    expect(input.integration).toBeUndefined()
  })
})

describe('cellState', () => {
  const open: OtaCell = { date: '2026-10-05', available: 3, price: '352000.00', min_los: null, max_los: null,
    closed_to_arrival: false, closed_to_departure: false, stop_sell: false }

  it('tells what a guest could book on that night', () => {
    expect(cellState(null)).toBe('missing')
    expect(cellState(open)).toBe('open')
    expect(cellState({ ...open, available: 0 })).toBe('soldout')
    expect(cellState({ ...open, stop_sell: true })).toBe('closed')
    expect(cellState({ ...open, price: null })).toBe('closed')
  })
})
