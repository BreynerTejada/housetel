import { useTranslation } from 'react-i18next'
import { formatDate, normalizeLang, parseDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { SireDay, SireDayState } from '../lib/sire'

const FILL: Record<SireDayState, string> = {
  reported: 'bg-success',
  toUpload: 'bg-warning',
  missing: 'bg-surface border-2 border-danger',
  clear: 'bg-surface-3',
}

/** Signature of the SIRE view: one bar per day, colored by its reporting state. */
export function SireDayStrip({
  days,
  size = 'md',
  legend = false,
  className,
}: {
  days: SireDay[]
  size?: 'sm' | 'md'
  legend?: boolean
  className?: string
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const counts = days.reduce<Record<SireDayState, number>>(
    (acc, day) => ({ ...acc, [day.state]: acc[day.state] + 1 }),
    { reported: 0, toUpload: 0, missing: 0, clear: 0 },
  )
  const summary = t('sire.strip.summary', {
    reported: counts.reported,
    toUpload: counts.toUpload,
    missing: counts.missing,
  })
  const first = days[0]?.date
  const last = days.at(-1)?.date
  return (
    <div className={cn('grid gap-2', className)}>
      <div role="img" aria-label={summary} className={cn('flex items-end gap-[3px]', size === 'sm' ? 'h-7' : 'h-11')}>
        {days.map((day) => (
          <span
            key={day.date}
            title={`${formatDate(day.date, lang === 'es' ? 'EEE d MMM' : 'EEE, MMM d', lang)} · ${t(`sire.strip.${day.state}`)}`}
            data-state={day.state}
            className={cn(
              'min-w-0 flex-1 rounded-[3px]',
              FILL[day.state],
              day.state === 'clear' ? 'h-1/2' : 'h-full',
              parseDate(day.date)?.getDay() === 1 && 'ml-[3px]',
            )}
          />
        ))}
      </div>
      {size === 'md' && first && last && (
        <div className="flex justify-between text-2xs text-subtle num">
          <span>{formatDate(first, 'd MMM', lang)}</span>
          <span>{formatDate(last, 'd MMM', lang)}</span>
        </div>
      )}
      {legend && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          {(['reported', 'toUpload', 'missing', 'clear'] as const).map((state) => (
            <li key={state} className="flex items-center gap-1.5">
              <span aria-hidden className={cn('inline-block size-2.5 rounded-[2px]', FILL[state])} />
              {t(`sire.strip.${state}`)}
              <span className="num font-semibold text-fg">{counts[state]}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
