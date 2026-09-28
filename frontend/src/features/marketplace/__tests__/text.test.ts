import { describe, expect, it } from 'vitest'
import i18n from '@/lib/i18n'
import type { CancellationPolicy } from '../api'
import { bedsLabel, guestsLabel, policySummary, tr } from '../lib/text'

const t = i18n.getFixedT('es', 'marketplace')
const tEn = i18n.getFixedT('en', 'marketplace')

const policy = (overrides: Partial<CancellationPolicy>): CancellationPolicy => ({
  name: { es: 'Flexible 48h' },
  description: {},
  non_refundable: false,
  free_until_hours_before: 48,
  penalty_type: 'first_night',
  penalty_value: '0.00',
  ...overrides,
})

describe('policySummary', () => {
  it('says until when cancelling is free and what it costs afterwards', () => {
    expect(policySummary(policy({}), t)).toEqual({
      tone: 'free',
      title: 'Cancelación gratis hasta 2 días antes de la llegada',
      detail: 'Después se cobra la primera noche.',
    })
    expect(policySummary(policy({ free_until_hours_before: 36, penalty_type: 'percent', penalty_value: '50.00' }), t)).toEqual({
      tone: 'free',
      title: 'Cancelación gratis hasta 36 horas antes de la llegada',
      detail: 'Después se cobra el 50 % de la reserva.',
    })
  })

  it('warns when every cancellation has a cost', () => {
    expect(policySummary(policy({ free_until_hours_before: 0, penalty_type: 'full' }), t)).toEqual({
      tone: 'partial',
      title: 'Cancelación con costo',
      detail: 'Si cancelas se cobra el total de la reserva.',
    })
    expect(policySummary(policy({ non_refundable: true }), t)).toEqual({
      tone: 'strict',
      title: 'No reembolsable',
      detail: 'Si cancelas se cobra el total de la reserva.',
    })
  })

  it('treats a plan without a policy as free cancellation (the hotel charges nothing)', () => {
    expect(policySummary(null, t).tone).toBe('free')
  })

  it('speaks English too', () => {
    expect(policySummary(policy({ free_until_hours_before: 24 }), tEn).title).toBe('Free cancellation until 1 day before arrival')
  })
})

describe('labels', () => {
  it('describes the party', () => {
    expect(guestsLabel(2, 0, t)).toBe('2 adultos')
    expect(guestsLabel(1, 1, t)).toBe('1 adulto · 1 niño')
    expect(guestsLabel(3, 2, tEn)).toBe('3 adults · 2 children')
  })

  it('lists the beds with their count', () => {
    expect(bedsLabel([{ type: 'king', count: 1 }, { type: 'sofa_bed', count: 1 }], t)).toBe('1 cama king · 1 sofá cama')
    expect(bedsLabel([{ type: 'bunk', count: 3 }], tEn)).toBe('3 bunk beds')
    expect(bedsLabel([], t)).toBe('')
  })

  it('reads translated texts with a Spanish fallback', () => {
    expect(tr({ es: 'Hola', en: 'Hello' }, 'en')).toBe('Hello')
    expect(tr({ es: 'Hola' }, 'en')).toBe('Hola')
    expect(tr(null, 'es')).toBe('')
  })
})
