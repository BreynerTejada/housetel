// API dates are `YYYY-MM-DD` calendar days: never go through UTC midnight.

function toParts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split('-').map(Number)
  return [y, m, d]
}

function fromDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = toParts(iso)
  return fromDate(new Date(y, m - 1, d + days))
}

/** Monday = 0 … Sunday = 6. */
export function weekdayOf(iso: string): number {
  const [y, m, d] = toParts(iso)
  return (new Date(y, m - 1, d).getDay() + 6) % 7
}

/** Hotels sell the weekend as the nights of Friday and Saturday. */
export function isWeekendNight(iso: string): boolean {
  const day = weekdayOf(iso)
  return day === 4 || day === 5
}
