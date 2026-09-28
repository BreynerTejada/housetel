import { useCallback, useEffect, useState } from 'react'

/**
 * A resend-style cooldown: `[secondsLeft, start]`. `start()` blocks the action for `seconds`; the value
 * ticks down once a second and is 0 when the action is available again.
 */
export function useCooldown(seconds: number): [number, () => void] {
  const [until, setUntil] = useState(0)
  const [now, setNow] = useState(0)
  const remaining = Math.max(0, Math.ceil((until - now) / 1000))

  useEffect(() => {
    if (remaining <= 0) return
    const id = window.setTimeout(() => setNow(Date.now()), 1000)
    return () => window.clearTimeout(id)
  }, [remaining, now])

  const start = useCallback(() => {
    const started = Date.now()
    setNow(started)
    setUntil(started + seconds * 1000)
  }, [seconds])

  return [remaining, start]
}
