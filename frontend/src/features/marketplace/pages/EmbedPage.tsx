import { ArrowUpRight } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { LoadingState } from '@/components/LoadingState'
import { fieldBase } from '@/components/ui/input'
import { formatDate, normalizeLang, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useEngineConfig } from '../api'
import { HotelMark } from '../components/EngineShell'
import { useBrandTheme } from '../lib/useBrandTheme'

const FIELD = cn(fieldBase, 'h-10 px-2.5 text-sm')

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`)
  date.setDate(date.getDate() + days)
  return toISODate(date)
}

/**
 * `/embed/:slug` — the search box a hotel pastes into its own website (an iframe, see the snippet in the booking
 * engine settings). Native date and number controls, because pickers must not be clipped by the iframe; it opens
 * the hotel's engine with the stay in a new tab (a plain GET form, so it works even before the app loads fully).
 */
export default function EmbedPage() {
  const { slug = '' } = useParams()
  const { t, i18n } = useTranslation('marketplace')
  const lang = normalizeLang(i18n.language)
  const uid = useId()
  const config = useEngineConfig(slug)
  useBrandTheme(config.data?.primary_color)
  const today = toISODate(new Date())
  const [checkin, setCheckin] = useState(() => addDays(today, 1))
  const [checkout, setCheckout] = useState(() => addDays(today, 3))
  const [problem, setProblem] = useState('')
  const invalid = Boolean(problem)

  if (config.isPending) return <LoadingState className="h-dvh" />
  const hotel = config.data
  if (!hotel || !hotel.enabled) {
    return <p className="grid h-dvh place-items-center p-4 text-center text-sm text-muted">{t('embed.unavailable')}</p>
  }
  const earliest = hotel.booking.earliest_checkin
  const latest = hotel.booking.latest_checkin

  function submit(event: FormEvent<HTMLFormElement>) {
    let message = ''
    if (!checkin || !checkout || checkout <= checkin) message = t('embed.invalidDates')
    else if (checkin < earliest) message = t('hotel.errors.too_soon', { date: formatDate(earliest, undefined, lang) })
    else if (checkin > latest) message = t('hotel.errors.too_far', { date: formatDate(latest, undefined, lang) })
    if (message) {
      event.preventDefault()
      setProblem(message)
    }
  }

  return (
    <div className="flex h-dvh flex-col justify-center bg-surface p-3 sm:px-4">
      <form
        role="search"
        aria-label={t('embed.title', { hotel: hotel.name })}
        method="get"
        action={`/h/${encodeURIComponent(slug)}`}
        target="_blank"
        noValidate
        onSubmit={submit}
        className="grid gap-2.5"
      >
        <div className="flex items-center gap-2.5">
          <HotelMark config={hotel} className="size-7 text-xs" />
          <p className="truncate text-sm font-bold text-fg">{t('embed.title', { hotel: hotel.name })}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_5.5rem_5.5rem_auto] sm:items-end">
          <label className="grid gap-1 text-xs font-semibold text-muted">
            {t('embed.checkin')}
            <input
              id={`${uid}-in`}
              type="date"
              name="checkin"
              required
              min={earliest}
              max={latest}
              value={checkin}
              onChange={(event) => {
                setCheckin(event.target.value)
                setProblem('')
              }}
              className={cn(FIELD, 'num')}
            />
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted">
            {t('embed.checkout')}
            <input
              id={`${uid}-out`}
              type="date"
              name="checkout"
              required
              min={checkin || earliest}
              value={checkout}
              aria-invalid={invalid}
              onChange={(event) => {
                setCheckout(event.target.value)
                setProblem('')
              }}
              className={cn(FIELD, 'num')}
            />
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted">
            {t('embed.adults')}
            <select name="adults" defaultValue="2" className={FIELD}>
              {Array.from({ length: 10 }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  {index + 1}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted">
            {t('embed.children')}
            <select name="children" defaultValue="0" className={FIELD}>
              {Array.from({ length: 7 }, (_, index) => (
                <option key={index} value={index}>
                  {index}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="col-span-2 inline-flex h-10 items-center justify-center gap-1.5 rounded-md bg-accent px-4 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 sm:col-span-1"
          >
            {t('embed.submit')}
            <ArrowUpRight aria-hidden className="size-4" />
            <span className="sr-only">({t('embed.newTab')})</span>
          </button>
        </div>
        {problem && (
          <p role="alert" className="text-xs font-medium text-danger-ink">
            {problem}
          </p>
        )}
      </form>
    </div>
  )
}
