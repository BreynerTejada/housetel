import type { CSSProperties } from 'react'

const HEX = /^#[0-9a-f]{6}$/i
const WHITE = '#ffffff'
const INK = '#1f1c19' // --text of the light theme

export function isHexColor(value: string | null | undefined): value is string {
  return typeof value === 'string' && HEX.test(value)
}

function channel(value: number): number {
  const srgb = value / 255
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4
}

/** WCAG relative luminance of a `#RRGGBB` color. */
export function luminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16)
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
}

/** WCAG contrast ratio between two `#RRGGBB` colors (1 to 21). */
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (light + 0.05) / (dark + 0.05)
}

/** White or near-black text, whichever reads better on `hex`. */
export function readableTextOn(hex: string): string {
  return contrastRatio(hex, WHITE) >= contrastRatio(hex, INK) ? WHITE : INK
}

/**
 * The hotel's color as the accent of its guest-facing pages (booking engine, widget): every accent token of the
 * design system is derived from it, so buttons, focus rings, selected days and soft backgrounds follow the brand
 * in both themes. An invalid color keeps the Housetel accent.
 */
export function brandStyle(color: string | null | undefined): CSSProperties {
  if (!isHexColor(color)) return {}
  const hex = color.toUpperCase()
  return {
    '--brand': hex,
    '--accent': hex,
    '--accent-hover': `color-mix(in srgb, ${hex} 84%, #000)`,
    '--accent-soft': `color-mix(in srgb, ${hex} 14%, var(--surface))`,
    '--accent-ink': `color-mix(in srgb, ${hex} 72%, var(--text))`,
    '--on-accent': readableTextOn(hex),
    '--focus': `color-mix(in srgb, ${hex} 70%, transparent)`,
  } as CSSProperties
}
