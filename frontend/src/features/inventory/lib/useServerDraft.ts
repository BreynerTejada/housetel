import { useState } from 'react'

/**
 * Form state for editing a record the server may change at any time (housekeeping changes a room's status
 * all day). When a newer `version` of the record arrives — the refetch after a save, or someone else's
 * change — the fields the user has not touched take the new values and the user's edits stay: the editor
 * never loses what is being typed nor remounts (so it keeps its open tab).
 */
export function useServerDraft<T extends object>(server: T, version: string) {
  const [state, setState] = useState(() => ({ version, baseline: server, draft: server }))
  let current = state
  if (state.version !== version) {
    // adjust state while rendering (react.dev "you might not need an effect"): no stale frame is shown
    current = { version, baseline: server, draft: rebase(state.draft, state.baseline, server) }
    setState(current)
  }
  return {
    baseline: current.baseline,
    draft: current.draft,
    setDraft: (update: (draft: T) => T) => setState((value) => ({ ...value, draft: update(value.draft) })),
    /** The record as a save answered it: it becomes both the baseline and the draft. */
    reset: (next: T, nextVersion: string) => setState({ version: nextVersion, baseline: next, draft: next }),
    discard: () => setState((value) => ({ ...value, draft: value.baseline })),
  }
}

/** `next` with the top-level fields the user changed (`draft` differs from `base`) kept from `draft`. */
export function rebase<T extends object>(draft: T, base: T, next: T): T {
  const result = { ...next }
  for (const key of Object.keys(draft) as (keyof T)[]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(base[key])) result[key] = draft[key]
  }
  return result
}
