export type PartOfDay = 'morning' | 'afternoon' | 'evening'

/** Morning 5:00–11:59, afternoon 12:00–18:59, evening otherwise — in the hotel's timezone. */
export function partOfDay(now: Date, timeZone: string): PartOfDay {
  let hour: number
  try {
    hour = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone }).format(now))
  } catch {
    hour = now.getHours()
  }
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 19) return 'afternoon'
  return 'evening'
}

export function firstName(fullName: string | null | undefined): string {
  return (fullName ?? '').trim().split(/\s+/)[0] ?? ''
}
