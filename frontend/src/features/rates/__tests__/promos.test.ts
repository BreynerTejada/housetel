import { describe, expect, it } from 'vitest'
import type { PromoCode } from '../api'
import { promoState } from '../lib/promos'

const base: PromoCode = {
  id: 'p',
  code: 'BIENVENIDA10',
  discount_type: 'percent',
  value: '10.00',
  valid_from: '2026-09-01',
  valid_to: '2026-12-31',
  stay_from: null,
  stay_to: null,
  rate_plans: [],
  max_uses: 100,
  uses: 3,
  is_active: true,
}

describe('promo code state on the business date', () => {
  it('is active inside its booking window (both ends inclusive)', () => {
    expect(promoState(base, '2026-09-25')).toBe('active')
    expect(promoState(base, '2026-09-01')).toBe('active')
    expect(promoState(base, '2026-12-31')).toBe('active')
    expect(promoState({ ...base, valid_from: null, valid_to: null, max_uses: null }, '2030-01-01')).toBe('active')
  })

  it('is scheduled before the window and expired after it', () => {
    expect(promoState(base, '2026-08-31')).toBe('scheduled')
    expect(promoState(base, '2027-01-01')).toBe('expired')
  })

  it('is used up when no uses are left, and paused when switched off', () => {
    expect(promoState({ ...base, uses: 100 }, '2026-09-25')).toBe('exhausted')
    expect(promoState({ ...base, is_active: false }, '2026-09-25')).toBe('inactive')
  })
})
