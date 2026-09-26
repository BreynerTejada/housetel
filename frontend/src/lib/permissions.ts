/**
 * Permission matching with the same semantics as the backend
 * (`apps/core/permissions.codes_match`, Python `fnmatch.fnmatchcase`):
 * `*` grants everything, exact codes match, and grants may be shell-style
 * patterns (`bookings.*`, `*.view`, `finance.re?und`, `finance.[!v]*`).
 */

import { useCallback } from 'react'
import { useActiveMembership } from './auth'

const compiled = new Map<string, RegExp>()

function escapeLiteral(ch: string): string {
  return ch.replace(/[.*+?^${}()|[\]\\/-]/g, '\\$&')
}

/** Port of Python's fnmatch.translate (case-sensitive, anchored). */
function fnmatchToRegExp(pattern: string): RegExp {
  let re = ''
  let i = 0
  const n = pattern.length
  while (i < n) {
    const ch = pattern[i++]
    if (ch === '*') {
      re += '.*'
    } else if (ch === '?') {
      re += '.'
    } else if (ch === '[') {
      let j = i
      if (j < n && pattern[j] === '!') j++
      if (j < n && pattern[j] === ']') j++
      while (j < n && pattern[j] !== ']') j++
      if (j >= n) {
        re += '\\['
      } else {
        let set = pattern.slice(i, j).replace(/\\/g, '\\\\')
        i = j + 1
        if (set.startsWith('!')) set = `^${set.slice(1)}`
        else if (set.startsWith('^')) set = `\\${set}`
        re += `[${set}]`
      }
    } else {
      re += escapeLiteral(ch)
    }
  }
  return new RegExp(`^${re}$`, 's')
}

function patternMatches(pattern: string, code: string): boolean {
  let re = compiled.get(pattern)
  if (!re) {
    re = fnmatchToRegExp(pattern)
    compiled.set(pattern, re)
  }
  return re.test(code)
}

export function matchPermission(granted: readonly string[] | null | undefined, code: string): boolean {
  if (!granted?.length) return false
  return granted.some((g) => g === '*' || g === code || patternMatches(g, code))
}

/**
 * True when the active membership (the one owning the active property) grants `code`.
 * No code means "no permission required". Mirrors backend `HasPropertyPermission`.
 */
export function useCan(code?: string): boolean {
  const membership = useActiveMembership()
  return !code || matchPermission(membership?.permissions, code)
}

/** Stable checker for filtering lists of items that declare a `permission`. */
export function usePermissionChecker(): (code?: string) => boolean {
  const membership = useActiveMembership()
  return useCallback((code?: string) => !code || matchPermission(membership?.permissions, code), [membership])
}
