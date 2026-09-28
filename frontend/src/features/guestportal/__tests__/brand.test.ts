import { describe, expect, it } from 'vitest'
import { brandStyle, brandTokens, contrast, parseHex } from '../lib/brand'

const WHITE = parseHex('#ffffff')!
const LIGHT_SURFACE = WHITE
const DARK_SURFACE = parseHex('#1c1a18')!

describe('parseHex', () => {
  it('reads #RRGGBB and #RGB colors and rejects anything else', () => {
    expect(parseHex('#B4583B')).toEqual([180, 88, 59])
    expect(parseHex('#fff')).toEqual([255, 255, 255])
    expect(parseHex('')).toBeNull()
    expect(parseHex('red')).toBeNull()
    expect(parseHex(undefined)).toBeNull()
  })
})

describe('brandTokens', () => {
  it('gives no tokens without a valid hotel color (the portal keeps Housetel colors)', () => {
    expect(brandTokens('', 'light')).toBeNull()
    expect(brandTokens('#12', 'dark')).toBeNull()
  })

  it.each([
    ['#1E3A5F', 'light'],
    ['#1E3A5F', 'dark'],
    ['#F2C94C', 'light'],
    ['#F2C94C', 'dark'],
    ['#B4583B', 'light'],
    ['#FAFAFA', 'light'],
    ['#101010', 'dark'],
  ] as const)('keeps text readable for %s in the %s theme', (hex, theme) => {
    const tokens = brandTokens(hex, theme)!
    const surface = theme === 'light' ? LIGHT_SURFACE : DARK_SURFACE

    // text on the brand fill (buttons) and brand-colored text on the page (links, labels)
    expect(contrast(tokens.onAccent, tokens.accent)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(tokens.accentInk, surface)).toBeGreaterThanOrEqual(4.5)
    // the fill itself stands out from the surface (WCAG 1.4.11 non-text contrast)
    expect(contrast(tokens.accent, surface)).toBeGreaterThanOrEqual(3)
  })

  it('keeps a brand color that already works as it is', () => {
    expect(brandTokens('#B4583B', 'light')!.accent).toEqual([180, 88, 59])
  })
})

describe('brandStyle', () => {
  it('turns the tokens into the CSS variables the design system reads', () => {
    const style = brandStyle('#1E3A5F', 'light') as Record<string, string>

    expect(style['--accent']).toBe('#1e3a5f')
    expect(style['--on-accent']).toBe('#ffffff')
    expect(Object.keys(style).sort()).toEqual(
      ['--accent', '--accent-hover', '--accent-ink', '--accent-soft', '--focus', '--on-accent'].sort(),
    )
  })

  it('is undefined without a hotel color', () => {
    expect(brandStyle(null, 'light')).toBeUndefined()
  })
})
