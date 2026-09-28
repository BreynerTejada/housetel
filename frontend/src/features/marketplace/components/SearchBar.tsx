import { Search } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { toISODate } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import type { Destination } from '../api'
import type { Stay } from '../lib/search-params'
import { DestinationField } from './DestinationField'
import { GuestsPicker } from './GuestsPicker'

export interface SearchValue {
  city: string
  stay: Stay
}

type Variant = 'hero' | 'compact' | 'panel'

interface SearchBarProps {
  value: SearchValue
  onSubmit: (value: SearchValue) => void
  variant?: Variant
  /** Without it the bar only asks for dates and guests (a hotel's own page). */
  destinations?: Destination[]
  /** First and last selectable day (`YYYY-MM-DD`); by default from today on. */
  min?: string
  max?: string
  submitLabel?: string
  /** Extra content before the button (the hotel page adds its promo code). */
  children?: ReactNode
  className?: string
}

const FORM: Record<Variant, string> = {
  hero: 'gap-1 rounded-2xl border border-border bg-surface p-1.5 shadow-md md:grid-cols-[1.15fr_1.35fr_1fr_auto]',
  compact: 'gap-1 rounded-xl border border-border bg-surface p-1 shadow-xs md:grid-cols-[1.15fr_1.35fr_1fr_auto]',
  panel: 'gap-2',
}

const SEGMENT: Record<Variant, string> = {
  hero: 'rounded-xl px-4 py-2.5 hover:bg-surface-2 focus-within:bg-surface-2',
  compact: 'rounded-lg px-3 py-1.5 hover:bg-surface-2 focus-within:bg-surface-2',
  panel: 'rounded-lg border border-border bg-surface px-3 py-2 hover:border-border-strong focus-within:border-accent',
}

/** Segments after the first get a hairline divider on wide screens (hero and compact bars). */
const DIVIDER = 'md:before:absolute md:before:inset-y-3 md:before:-left-0.5 md:before:w-px md:before:bg-border'

const FIELD = 'h-auto w-full border-0 bg-transparent p-0 text-[15px] font-semibold shadow-none hover:border-0 focus-visible:ring-0'

/**
 * Destination, dates and guests. The hero and compact variants lay the fields out in one row on wide screens;
 * `panel` stacks them (sidebars). Submitting hands the value to the page, which decides where to go.
 */
export function SearchBar({ value, onSubmit, variant = 'hero', destinations, min, max, submitLabel, children, className }: SearchBarProps) {
  const { t } = useTranslation('marketplace')
  const uid = useId()
  const wide = useMediaQuery('(min-width: 640px)')
  const [city, setCity] = useState(value.city)
  const [stay, setStay] = useState(value.stay)
  // The page may change the value (back button, a new search): follow it. Compared by content, so a parent
  // that builds a new object on every render does not wipe what the person is typing.
  const valueKey = JSON.stringify(value)
  const [syncedKey, setSyncedKey] = useState(valueKey)
  if (syncedKey !== valueKey) {
    setSyncedKey(valueKey)
    setCity(value.city)
    setStay(value.stay)
  }

  const inline = variant !== 'panel'
  const segment = cn('relative flex min-w-0 flex-col justify-center gap-0.5 transition-colors', SEGMENT[variant])
  const label = cn('font-semibold text-muted', variant === 'compact' ? 'text-[11px]' : 'text-[12px]')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({ city: city.trim(), stay })
  }

  return (
    <form role="search" aria-label={t('search.label')} onSubmit={submit} className={cn('grid', FORM[variant], className)}>
      {destinations && (
        <div className={segment}>
          <label htmlFor={`${uid}-city`} className={label}>
            {t('search.destination')}
          </label>
          <DestinationField id={`${uid}-city`} value={city} onChange={setCity} destinations={destinations} />
        </div>
      )}
      <div className={cn(segment, inline && destinations && DIVIDER)}>
        <span id={`${uid}-dates`} className={label}>
          {t('search.dates')}
        </span>
        <DateRangePicker
          aria-label={t('search.dates')}
          value={stay.checkin && stay.checkout ? { from: stay.checkin, to: stay.checkout } : null}
          onChange={(range) => setStay({ ...stay, checkin: range?.from ?? null, checkout: range?.to ?? null })}
          min={min ?? toISODate(new Date())}
          max={max}
          minNights={1}
          showNights
          numberOfMonths={wide ? 2 : 1}
          placeholder={t('search.datesPlaceholder')}
          className={FIELD}
        />
      </div>
      <div className={cn(segment, inline && DIVIDER)}>
        <span id={`${uid}-guests`} className={label}>
          {t('search.guests')}
        </span>
        <GuestsPicker
          id={`${uid}-guests-value`}
          aria-labelledby={`${uid}-guests`}
          value={stay}
          onChange={(party) => setStay({ ...stay, ...party })}
          className="text-[15px] font-semibold"
        />
      </div>
      {children}
      <Button
        type="submit"
        variant="primary"
        size="lg"
        className={cn(
          'text-base',
          variant === 'hero' && 'h-12 rounded-xl px-7 md:h-auto',
          variant === 'compact' && 'h-11 rounded-lg px-5 md:h-auto',
          variant === 'panel' && 'h-11 w-full',
        )}
      >
        <Search aria-hidden className="size-[18px]" />
        {submitLabel ?? t('search.submit')}
      </Button>
    </form>
  )
}
