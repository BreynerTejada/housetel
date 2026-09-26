import { describe, expect, it } from 'vitest'
import { SESSION_STORAGE_KEY, useSession } from '@/lib/session'

describe('session store', () => {
  it('persists the selected property so it survives a reload', () => {
    useSession.getState().setPropertyId('prop-42')

    const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) ?? '{}')
    expect(stored.state.propertyId).toBe('prop-42')
    expect(useSession.getState().propertyId).toBe('prop-42')
  })
})
