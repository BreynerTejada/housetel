import type { PromoCode } from '../api'

export type PromoState = 'active' | 'inactive' | 'expired' | 'exhausted' | 'scheduled'

/**
 * What a guest would get today (`today` = business date, `YYYY-MM-DD`): an inactive code, one whose booking
 * window ended or has not started, one with no uses left, or an active one. Windows are inclusive.
 */
export function promoState(promo: PromoCode, today: string): PromoState {
  if (!promo.is_active) return 'inactive'
  if (promo.valid_to && promo.valid_to < today) return 'expired'
  if (promo.max_uses !== null && promo.uses >= promo.max_uses) return 'exhausted'
  if (promo.valid_from && promo.valid_from > today) return 'scheduled'
  return 'active'
}
