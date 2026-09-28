import { differenceInCalendarDays } from 'date-fns'
import type { BadgeTone } from '@/components/ui/badge'
import { parseDate } from '@/lib/format'
import type { GroupBlock, GroupFigures, GroupState, RoomingRow } from '../api'

/** Pure helpers of the groups pages (pilot P3). */

export const GROUP_STATE_TONE: Record<GroupState, BadgeTone> = {
  upcoming: 'info',
  in_house: 'accent',
  past: 'neutral',
  empty: 'stone',
}

/** Days from the business date to `day` (negative when it passed). */
export function daysUntil(day: string, bd: string): number {
  const target = parseDate(day)
  const today = parseDate(bd)
  if (!target || !today) return 0
  return differenceInCalendarDays(target, today)
}

/** How a block stands: released, releasing today, or days left before the release. */
export function releaseState(block: Pick<GroupBlock, 'released_at' | 'release_date'>, bd: string) {
  if (block.released_at) return { kind: 'released' as const, days: 0 }
  const days = daysUntil(block.release_date, bd)
  if (days <= 0) return { kind: 'due' as const, days: 0 }
  return { kind: 'pending' as const, days }
}

/** Tone of a pickup percentage: low (sand), halfway (slate), almost full (sage). */
export function pickupTone(pct: number | null | undefined): BadgeTone {
  if (pct === null || pct === undefined) return 'neutral'
  if (pct >= 80) return 'success'
  if (pct >= 40) return 'info'
  return 'warning'
}

/** Nights of a group (`figures.start` → `figures.end`), 0 without dates. */
export function groupNights(figures: GroupFigures | null | undefined): number {
  if (!figures?.start || !figures.end) return 0
  return Math.max(0, daysUntil(figures.end, figures.start))
}

/** Rooms of the rooming list that still have nobody named in them. */
export function unnamedRooms(rows: RoomingRow[]): number {
  return rows.filter((row) => !row.guest).length
}

/** "Ana María Pérez Gómez" → first name(s) and last name(s) for the rooming list (two last names in Colombia). */
export function splitName(full: string): { first_name: string; last_name: string } {
  const words = full.trim().split(/\s+/).filter(Boolean)
  if (words.length <= 1) return { first_name: words[0] ?? '', last_name: '' }
  if (words.length === 2) return { first_name: words[0]!, last_name: words[1]! }
  const cut = words.length >= 4 ? 2 : 1
  return { first_name: words.slice(0, cut).join(' '), last_name: words.slice(cut).join(' ') }
}
