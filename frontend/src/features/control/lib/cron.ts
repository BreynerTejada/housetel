/**
 * When does an automation fire during the day? Parses the minute and hour fields of the backend's cron string
 * (`schedule.cron`, e.g. "0 2 * * *", "*\/15 * * * *", "0 5,11,17,23 * * *") into minutes after midnight, for
 * the 24-hour rhythm rail. Day-of-month / weekday restrictions don't change the daily pattern drawn.
 */

export interface DailyPattern {
  /** Minutes after midnight (0–1439) of each run, sorted. Empty when `continuous`. */
  times: number[]
  /** Runs so often (≥ every 5 min) that the rail draws a band instead of ticks. */
  continuous: boolean
  /** Runs only on some days (weekday or day of month set). */
  someDays: boolean
}

function expand(field: string, max: number): number[] | null {
  const values = new Set<number>()
  for (const raw of field.split(',')) {
    const part = raw.trim()
    if (part === '*') {
      for (let v = 0; v < max; v++) values.add(v)
      continue
    }
    const step = part.match(/^(\*|\d+-\d+)\/(\d+)$/)
    if (step) {
      const every = Number(step[2])
      if (!every) return null
      const [from, to] = step[1] === '*' ? [0, max - 1] : step[1].split('-').map(Number)
      for (let v = from; v <= Math.min(to, max - 1); v += every) values.add(v)
      continue
    }
    const range = part.match(/^(\d+)-(\d+)$/)
    if (range) {
      for (let v = Number(range[1]); v <= Math.min(Number(range[2]), max - 1); v++) values.add(v)
      continue
    }
    if (/^\d+$/.test(part) && Number(part) < max) {
      values.add(Number(part))
      continue
    }
    return null
  }
  return [...values].sort((a, b) => a - b)
}

export function dailyPattern(cron: string | null | undefined, everySeconds?: number | null): DailyPattern | null {
  if (everySeconds) {
    const step = Math.max(1, Math.round(everySeconds / 60))
    if (step <= 5) return { times: [], continuous: true, someDays: false }
    const times: number[] = []
    for (let m = 0; m < 1440; m += step) times.push(m)
    return { times, continuous: false, someDays: false }
  }
  if (!cron) return null
  const [minute, hour, dom = '*', month = '*', dow = '*'] = cron.trim().split(/\s+/)
  if (minute === undefined || hour === undefined) return null
  const minutes = expand(minute, 60)
  const hours = expand(hour, 24)
  if (!minutes || !hours) return null
  const someDays = dom !== '*' || dow !== '*' || month !== '*'
  if (minutes.length * hours.length > 288) return { times: [], continuous: true, someDays }
  const times = hours.flatMap((h) => minutes.map((m) => h * 60 + m)).sort((a, b) => a - b)
  return { times, continuous: false, someDays }
}

/** Minutes after midnight "now" in the hotel's time zone. */
export function minutesNow(timeZone: string | undefined, now: Date = new Date()): number {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now)
    const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? 0)
    const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? 0)
    return hour * 60 + minute
  } catch {
    return now.getHours() * 60 + now.getMinutes()
  }
}

export function formatClock(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24
  const m = minutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** "02:00": time of day of an ISO datetime in the hotel's time zone (the rail and the schedules use hotel time). */
export function hotelClock(value: string | null | undefined, timeZone: string | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  try {
    return new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date)
  } catch {
    return formatClock(date.getHours() * 60 + date.getMinutes())
  }
}
