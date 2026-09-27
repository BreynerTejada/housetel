import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Holiday, Season, WeekdayKey } from '../../api'
import { monthCells, seasonOn, WEEKDAY_KEYS } from '../../lib/plans'

const MONTHS = Array.from({ length: 12 }, (_, month) => month)

/**
 * The year at a glance: every night painted with the season that prices it (highest priority wins, end
 * dates inclusive), holidays dotted and the business date outlined. The selected season reads stronger.
 */
export function YearCalendar({
  year,
  onYearChange,
  seasons,
  holidays,
  selectedId,
  today,
}: {
  year: number
  onYearChange: (year: number) => void
  seasons: Season[]
  holidays: Holiday[]
  selectedId: string | null
  today: string
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const holidayNames = useMemo(() => new Map(holidays.map((holiday) => [holiday.date, holiday.name])), [holidays])

  return (
    <section aria-label={t('plans.seasons.calendarLabel', { year })} className="rounded-lg border border-border bg-surface p-4 shadow-xs">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-bold tracking-[-0.01em] text-fg">{t('plans.seasons.calendarTitle', { year })}</h3>
        <div className="flex items-center gap-1">
          <Button size="icon-sm" variant="ghost" aria-label={t('plans.seasons.previousYear')} onClick={() => onYearChange(year - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <span className="num w-12 text-center text-sm font-bold text-fg">{year}</span>
          <Button size="icon-sm" variant="ghost" aria-label={t('plans.seasons.nextYear')} onClick={() => onYearChange(year + 1)}>
            <ChevronRight aria-hidden />
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-x-5 gap-y-4 min-[420px]:grid-cols-2 md:grid-cols-3 2xl:grid-cols-4">
        {MONTHS.map((month) => (
          <Month
            key={month}
            year={year}
            month={month}
            seasons={seasons}
            holidayNames={holidayNames}
            selectedId={selectedId}
            today={today}
            lang={lang}
          />
        ))}
      </div>
    </section>
  )
}

function Month({
  year,
  month,
  seasons,
  holidayNames,
  selectedId,
  today,
  lang,
}: {
  year: number
  month: number
  seasons: Season[]
  holidayNames: Map<string, string>
  selectedId: string | null
  today: string
  lang: 'es' | 'en'
}) {
  const { t } = useTranslation('rates')
  const cells = monthCells(year, month)
  const weeks: (string | null)[][] = []
  for (let index = 0; index < cells.length; index += 7) weeks.push(cells.slice(index, index + 7))
  const first = `${year}-${String(month + 1).padStart(2, '0')}-01`

  return (
    <table className="num w-full table-fixed border-separate border-spacing-[2px] text-center text-2xs">
      <caption className="mb-1 text-left text-xs font-bold text-fg capitalize">{formatDate(first, 'MMMM', lang)}</caption>
      <thead>
        <tr>
          {WEEKDAY_KEYS.map((key: WeekdayKey) => (
            <th key={key} scope="col" className="pb-0.5 font-semibold text-subtle">
              <span aria-hidden>{t(`daysShort.${key}`)}</span>
              <span className="sr-only">{t(`days.${key}`)}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {weeks.map((week, row) => (
          <tr key={row}>
            {week.map((day, column) => {
              if (!day) return <td key={column} />
              const season = seasonOn(seasons, day)
              const holiday = holidayNames.get(day)
              const label = [
                formatDate(day, 'EEE d MMM', lang),
                season?.name,
                holiday ? t('plans.seasons.holiday', { name: holiday }) : null,
              ]
                .filter(Boolean)
                .join(' · ')
              const selected = season !== null && season.id === selectedId
              return (
                <td
                  key={column}
                  aria-label={label}
                  title={label}
                  className={cn(
                    'relative h-6 rounded-[5px] align-middle text-fg',
                    selected && 'font-bold',
                    day === today && 'outline-2 -outline-offset-1 outline-accent',
                  )}
                  style={
                    season
                      ? {
                          backgroundColor: `color-mix(in srgb, ${season.color} ${selected ? 46 : 20}%, transparent)`,
                          boxShadow: selected ? `inset 0 0 0 1px ${season.color}` : undefined,
                        }
                      : undefined
                  }
                >
                  {Number(day.slice(8))}
                  {holiday && <span aria-hidden className="absolute bottom-0.5 left-1/2 size-1 -translate-x-1/2 rounded-full bg-accent-ink" />}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
