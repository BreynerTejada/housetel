import type { CSSProperties } from 'react'
import type { ResolvedTheme } from '@/lib/theme'

/**
 * The guest portal wears the hotel's color (`Property.branding.primary_color`). It overrides the design
 * system's accent variables on the portal root, so every shared component (buttons, focus rings, badges)
 * follows the hotel — without ever giving up legibility: the fill, the text on it and the brand-colored
 * text on the page are adjusted until they reach WCAG AA against the current theme.
 */

export type Rgb = [number, number, number]

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i
const WHITE: Rgb = [255, 255, 255]
const BLACK: Rgb = [0, 0, 0]
const ON_DARK_INK: Rgb = [0x1a, 0x14, 0x12] // the system's --on-accent in dark mode
const SURFACE: Record<ResolvedTheme, Rgb> = { light: [0xff, 0xff, 0xff], dark: [0x1c, 0x1a, 0x18] }
const TEXT: Record<ResolvedTheme, Rgb> = { light: [0x1f, 0x1c, 0x19], dark: [0xee, 0xea, 0xe4] }

export function parseHex(value: string | null | undefined): Rgb | null {
  const match = HEX.exec((value ?? '').trim())
  if (!match) return null
  const digits = match[1]!
  const full = digits.length === 3 ? [...digits].map((d) => d + d).join('') : digits
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as Rgb
}

export function toHex(rgb: Rgb): string {
  return `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`
}

function linear(channel: number): number {
  const s = channel / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

export function luminance([r, g, b]: Rgb): number {
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
}

/** WCAG contrast ratio (1–21). */
export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** `a` moved `amount` (0–1) of the way to `b`. */
export function mix(a: Rgb, b: Rgb, amount: number): Rgb {
  return a.map((channel, i) => Math.round(channel + (b[i]! - channel) * amount)) as Rgb
}

/** The first mix of `from` toward `to` (5 % steps) that reaches `ratio` against `against`. */
function reach(from: Rgb, to: Rgb, against: Rgb, ratio: number): Rgb {
  for (let step = 0; step <= 20; step++) {
    const candidate = mix(from, to, step * 0.05)
    if (contrast(candidate, against) >= ratio) return candidate
  }
  return to
}

function rgba([r, g, b]: Rgb, alpha: number): string {
  return `rgb(${r} ${g} ${b} / ${alpha})`
}

export interface BrandTokens {
  accent: Rgb
  accentHover: Rgb
  accentInk: Rgb
  onAccent: Rgb
  soft: string
  focus: string
}

export function brandTokens(hex: string | null | undefined, theme: ResolvedTheme): BrandTokens | null {
  const base = parseHex(hex)
  if (!base) return null
  const surface = SURFACE[theme]
  // the fill must stand out from the surface: darken it on light pages, lighten it on dark ones
  const accent = reach(base, theme === 'light' ? TEXT.light : WHITE, surface, 3)
  const dark = theme === 'light' ? TEXT.light : ON_DARK_INK
  const onAccent = contrast(WHITE, accent) >= contrast(dark, accent) ? WHITE : dark
  const accentHover = mix(accent, theme === 'light' ? BLACK : WHITE, 0.12)
  const accentInk = reach(accent, TEXT[theme], surface, 4.5)
  return {
    accent,
    accentHover,
    accentInk,
    onAccent,
    soft: rgba(accent, theme === 'light' ? 0.12 : 0.18),
    focus: rgba(accent, 0.7),
  }
}

/** Inline style for the portal root; `undefined` keeps the Housetel colors. */
export function brandStyle(hex: string | null | undefined, theme: ResolvedTheme): CSSProperties | undefined {
  const tokens = brandTokens(hex, theme)
  if (!tokens) return undefined
  return {
    '--accent': toHex(tokens.accent),
    '--accent-hover': toHex(tokens.accentHover),
    '--accent-ink': toHex(tokens.accentInk),
    '--on-accent': toHex(tokens.onAccent),
    '--accent-soft': tokens.soft,
    '--focus': tokens.focus,
  } as CSSProperties
}
