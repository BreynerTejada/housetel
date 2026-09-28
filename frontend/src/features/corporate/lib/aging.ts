import type { AgingKey } from '../api'

/**
 * Age bands are ordinal: one hue (the terracotta accent) in monotone lightness steps, light = recent, dark = old
 * (dark mode flips the anchor: the oldest band is the brightest). Validated with the dataviz ordinal checks
 * (monotone L, ΔL ≥ 0.06, light end ≥ 2:1 on the surface) for both themes.
 */
export const AGING_FILL: Record<AgingKey, string> = {
  current: 'bg-[#d99479] dark:bg-[#8a4b38]',
  d31_60: 'bg-[#c46c4c] dark:bg-[#b2634a]',
  d61_90: 'bg-[#a14c2e] dark:bg-[#d6846a]',
  d90_plus: 'bg-[#72301b] dark:bg-[#f0b39f]',
}
