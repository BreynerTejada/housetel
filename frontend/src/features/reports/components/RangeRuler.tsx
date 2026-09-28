import { useTranslation } from 'react-i18next'
import { formatDate, formatDateRange, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { rangeDates, type ReportRange } from '../lib/presets'

/** Beyond this many days a tick is a week (a year of daily ticks would not fit a phone). */
const WEEKLY_FROM = 120

interface Tick {
  key: string
  kind: 'actual' | 'forecast'
  today: boolean
  weekStart: boolean
}

function buildTicks(range: ReportRange, businessDate: string, forecast: boolean): Tick[] {
  const dates = rangeDates(range)
  if (dates.length <= WEEKLY_FROM) {
    return dates.map((date) => ({
      key: date,
      kind: forecast && date >= businessDate ? 'forecast' : 'actual',
      today: date === businessDate,
      weekStart: parseDate(date)?.getDay() === 1,
    }))
  }
  const weeks = new Map<string, string[]>()
  for (const date of dates) {
    const day = parseDate(date)!
    const monday = new Date(day)
    monday.setDate(day.getDate() - ((day.getDay() + 6) % 7))
    const key = toISODate(monday)
    weeks.set(key, [...(weeks.get(key) ?? []), date])
  }
  return [...weeks.entries()].map(([key, days]) => ({
    key,
    kind: forecast && days[0]! > businessDate ? 'forecast' : 'actual',
    today: days.includes(businessDate),
    weekStart: false,
  }))
}

/**
 * The range as something you can count: one tick per business day, both ends included. When the report mixes
 * actual and on-the-books figures, the days from the business date on take the forecast tone; the business
 * date itself carries the "today" notch. The comparison period (if any) runs underneath in gray.
 */
export function RangeRuler({
  range,
  compare,
  businessDate,
  forecast,
}: {
  range: ReportRange | null
  compare: ReportRange | null
  businessDate: string
  /** Whether nights from the business date on are a forecast in this report. */
  forecast: boolean
}) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)

  if (!range) {
    return (
      <p className="flex items-center gap-2 text-[13px] text-muted">
        <span aria-hidden className="h-4 w-1 rounded-full bg-accent" />
        {t('ruler.snapshot', { date: formatDate(businessDate, undefined, lang) })}
      </p>
    )
  }

  const ticks = buildTicks(range, businessDate, forecast)
  const days = rangeDates(range)
  const forecastDays = forecast ? days.filter((date) => date >= businessDate).length : 0
  const actualDays = days.length - forecastDays
  const todayIndex = ticks.findIndex((tick) => tick.today)
  const dense = ticks.length > 62
  const compareTicks = compare ? buildTicks(compare, businessDate, false) : []
  const single = days.length === 1

  const summary = [
    t('ruler.days', { count: days.length }),
    single ? t('ruler.singleDay') : t('ruler.inclusive'),
    ...(forecast && forecastDays > 0 && actualDays > 0
      ? [t('ruler.actual', { count: actualDays }), t('ruler.forecast', { count: forecastDays })]
      : []),
  ]

  return (
    <figure className="flex flex-col gap-1.5" aria-label={t('ruler.label')}>
      {!single && (
        <div aria-hidden className="relative">
          <div className={cn('range-ruler', dense && 'range-ruler--dense')} style={{ gap: dense ? 1 : 2 }}>
            {ticks.map((tick) => (
              <span
                key={tick.key}
                className="range-ruler__tick"
                data-kind={tick.kind}
                data-today={tick.today || undefined}
                data-week-start={tick.weekStart || undefined}
              />
            ))}
          </div>
          {compareTicks.length > 0 && (
            <div className="range-ruler range-ruler--compare mt-1" style={{ gap: compareTicks.length > 62 ? 1 : 2 }}>
              {compareTicks.map((tick) => (
                <span key={tick.key} className="range-ruler__tick" />
              ))}
            </div>
          )}
        </div>
      )}
      <figcaption className="flex flex-col gap-1 text-xs text-muted sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-3">
        <span className="num font-semibold text-fg">{formatDateRange(range.start, range.end, lang)}</span>
        <span>{summary.join(' · ')}</span>
        {todayIndex >= 0 && !single && (
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-3 w-[3px] rounded-full bg-accent" />
            {t('ruler.today')} {formatDate(businessDate, lang === 'en' ? 'MMM d' : 'd MMM', lang)}
          </span>
        )}
        {compare && (
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-[5px] w-3 rounded-full bg-[var(--viz-compare)]" />
            {t('ruler.compareWith', { range: formatDateRange(compare.start, compare.end, lang) })}
          </span>
        )}
      </figcaption>
    </figure>
  )
}
