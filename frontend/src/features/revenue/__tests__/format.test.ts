import { describe, expect, it } from 'vitest'
import { compactMoney, pick, signedPercent } from '../lib/format'

describe('signedPercent', () => {
  it('writes the sign, the true minus and the decimal separator of each language', () => {
    expect(signedPercent(12, 'es')).toBe('+12 %')
    expect(signedPercent('-4.25', 'es')).toBe('−4,25 %')
    expect(signedPercent('-4.25', 'en')).toBe('−4.25 %')
    expect(signedPercent('0.00', 'es')).toBe('0 %')
  })

  it('can leave out the percent sign for tight cells', () => {
    expect(signedPercent('15.00', 'es', { unit: false })).toBe('+15')
    expect(signedPercent('-2.5', 'es', { unit: false })).toBe('−2,5')
  })
})

describe('compactMoney', () => {
  it('shortens millions and thousands the way each language reads them', () => {
    expect(compactMoney('2365400.00', 'es')).toBe('$ 2,4 M')
    expect(compactMoney('-4767200', 'es')).toBe('−$ 4,8 M')
    expect(compactMoney('950000', 'es')).toBe('$ 950 mil')
    expect(compactMoney('2365400.00', 'en')).toBe('$2.4M')
    expect(compactMoney('950000', 'en')).toBe('$950K')
    expect(compactMoney('1440000000', 'en')).toBe('$1.4B')
    expect(compactMoney('1440000000', 'es')).toBe('$ 1.440 M')
  })

  it('keeps small amounts whole', () => {
    expect(compactMoney('850', 'es')).toBe('$ 850')
    expect(compactMoney('0.00', 'en')).toBe('$0')
  })
})

describe('pick', () => {
  it('reads a translated field in the language on screen, falling back to Spanish', () => {
    expect(pick({ es: 'Estándar', en: 'Standard' }, 'en')).toBe('Standard')
    expect(pick({ es: 'Estándar', en: '' }, 'en')).toBe('Estándar')
    expect(pick(null, 'es')).toBe('')
  })
})
