import { describe, expect, it } from 'vitest'
import { cn } from '@/lib/utils'

describe('cn', () => {
  it('lets the later class win within the same utility group', () => {
    expect(cn('bg-surface px-2', 'bg-surface-2')).toBe('px-2 bg-surface-2')
    expect(cn('text-muted', 'text-accent')).toBe('text-accent')
  })

  it('keeps the custom 2xs font size next to a text color', () => {
    expect(cn('text-2xs', 'text-muted')).toBe('text-2xs text-muted')
    expect(cn('text-2xs', 'text-sm')).toBe('text-sm')
  })

  it('drops falsy values', () => {
    expect(cn('a', false, undefined, null, '', 'b')).toBe('a b')
  })
})
