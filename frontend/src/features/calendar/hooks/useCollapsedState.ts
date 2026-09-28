import { useCallback, useMemo } from 'react'
import { useLocalStorageState } from '@/lib/hooks'
import { resolveCollapsed } from '../lib/layout'

export const COLLAPSED_STORAGE_KEY = 'housetel.calendar.collapsed'

function isOverrides(value: unknown): value is Record<string, boolean> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Folded categories and unassigned groups. The user's choices are remembered per browser as overrides
 * (`key → folded?`), so the data-driven defaults keep applying to every group the user never touched.
 */
export function useCollapsedState(defaults: ReadonlySet<string>) {
  const [stored, setStored] = useLocalStorageState<Record<string, boolean>>(COLLAPSED_STORAGE_KEY, {})
  const overrides = useMemo(() => (isOverrides(stored) ? stored : {}), [stored])
  const collapsed = useMemo(() => resolveCollapsed(defaults, overrides), [defaults, overrides])
  const toggle = useCallback(
    (key: string) => setStored({ ...overrides, [key]: !collapsed.has(key) }),
    [collapsed, overrides, setStored],
  )
  /** Folds or unfolds several groups at once (e.g. to reach a search match). */
  const setFolded = useCallback(
    (keys: readonly string[], folded: boolean) => setStored({ ...overrides, ...Object.fromEntries(keys.map((key) => [key, folded])) }),
    [overrides, setStored],
  )
  return { collapsed, toggle, setFolded }
}
