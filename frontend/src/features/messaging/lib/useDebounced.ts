import { useEffect, useState } from 'react'

/**
 * `value` once it stopped changing for `delay` ms (live previews while typing). Compared by content, so an
 * object rebuilt on every render does not restart the timer.
 */
export function useDebounced<T>(value: T, delay = 350): T {
  const serialized = JSON.stringify(value)
  const [debounced, setDebounced] = useState(serialized)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(serialized), delay)
    return () => window.clearTimeout(id)
  }, [serialized, delay])
  return JSON.parse(debounced) as T
}
