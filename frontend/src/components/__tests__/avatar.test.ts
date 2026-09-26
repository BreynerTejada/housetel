import { describe, expect, it } from 'vitest'
import { initials } from '@/components/ui/avatar'

describe('initials', () => {
  it('uses the first letters of the first and last names', () => {
    expect(initials('Valentina Ríos')).toBe('VR')
    expect(initials('maría josé gómez')).toBe('MG')
  })

  it('uses a single letter for one-word names', () => {
    expect(initials('Recepción')).toBe('R')
  })

  it('falls back to the email when there is no name', () => {
    expect(initials('  ', 'owner@casaaurora.co')).toBe('O')
    expect(initials(null, null)).toBe('?')
  })
})
