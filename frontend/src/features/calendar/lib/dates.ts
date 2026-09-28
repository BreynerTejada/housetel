// Calendar days as `YYYY-MM-DD` strings. Arithmetic runs on UTC day numbers so no time zone or DST rule
// can shift a date (API dates are calendar days of the property, never instants).

const DAY_MS = 86_400_000

function dayNumber(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return Date.UTC(y, m - 1, d) / DAY_MS
}

function fromDayNumber(n: number): string {
  const date = new Date(n * DAY_MS)
  const y = date.getUTCFullYear()
  const m = String(date.getUTCMonth() + 1).padStart(2, '0')
  const d = String(date.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function addDays(iso: string, days: number): string {
  return fromDayNumber(dayNumber(iso) + days)
}

/** Days from `from` to `to` (negative when `to` is earlier). */
export function diffDays(from: string, to: string): number {
  return dayNumber(to) - dayNumber(from)
}

export function dayList(start: string, count: number): string[] {
  const first = dayNumber(start)
  return Array.from({ length: Math.max(0, count) }, (_, i) => fromDayNumber(first + i))
}

/** Monday = 0 … Sunday = 6 (the API convention). */
export function weekdayOf(iso: string): number {
  return (new Date(dayNumber(iso) * DAY_MS).getUTCDay() + 6) % 7
}

/** Hotels sell the weekend as the nights of Friday and Saturday (same rule as the rate grid). */
export function isWeekendNight(iso: string): boolean {
  const day = weekdayOf(iso)
  return day === 4 || day === 5
}

/** Years touched by the half-open range `[start, end)`. */
export function yearsBetween(start: string, end: string): number[] {
  const first = Number(start.slice(0, 4))
  const last = Number(addDays(end, -1).slice(0, 4))
  const years: number[] = []
  for (let year = first; year <= last; year += 1) years.push(year)
  return years
}
