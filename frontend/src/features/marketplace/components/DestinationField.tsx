import { MapPin } from 'lucide-react'
import { useId, useMemo, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Destination } from '../api'
import { normalizePlace, placeFor, thermalFloor } from '../lib/places'

interface DestinationFieldProps {
  id: string
  value: string
  onChange: (city: string) => void
  destinations: Destination[]
  placeholder?: string
  className?: string
  inputClassName?: string
}

/**
 * Free-text destination with suggestions (the cities that have hotels in Housetel): typing filters them,
 * arrows move, Enter picks, Escape closes. The typed text is searched as is when nothing is picked.
 */
export function DestinationField({ id, value, onChange, destinations, placeholder, className, inputClassName }: DestinationFieldProps) {
  const { t, i18n } = useTranslation('marketplace')
  const lang = normalizeLang(i18n.language)
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)

  const options = useMemo(() => {
    const query = normalizePlace(value)
    const matches = destinations.filter((destination) => {
      const city = normalizePlace(destination.city)
      return !query || city.includes(query) || normalizePlace(destination.department).includes(query)
    })
    // exactly what is written already: nothing to suggest
    return matches.length === 1 && normalizePlace(matches[0]!.city) === query ? [] : matches
  }, [destinations, value])

  const expanded = open && options.length > 0

  function pick(city: string) {
    onChange(city)
    setOpen(false)
    setActive(-1)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActive((current) => (options.length ? (current + 1) % options.length : -1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((current) => (options.length ? (current <= 0 ? options.length - 1 : current - 1) : -1))
    } else if (event.key === 'Enter' && expanded && active >= 0) {
      event.preventDefault()
      pick(options[active]!.city)
    } else if (event.key === 'Escape' && expanded) {
      event.preventDefault()
      setOpen(false)
      setActive(-1)
    }
  }

  return (
    <div className={cn('relative', className)}>
      <div className="flex items-center gap-2">
        <MapPin aria-hidden className="size-4 shrink-0 text-accent" />
        <input
          id={id}
          type="text"
          name="city"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-activedescendant={expanded && active >= 0 ? `${listId}-${active}` : undefined}
          value={value}
          placeholder={placeholder ?? t('search.destinationPlaceholder')}
          onChange={(event) => {
            onChange(event.target.value)
            setOpen(true)
            setActive(-1)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          className={cn('w-full min-w-0 bg-transparent text-[15px] font-semibold text-fg outline-none placeholder:font-medium', inputClassName)}
        />
      </div>
      <ul
        id={listId}
        role="listbox"
        aria-label={t('search.suggestions')}
        hidden={!expanded}
        className="absolute top-full left-0 z-40 mt-3 w-[min(22rem,calc(100vw-3rem))] overflow-hidden rounded-xl border border-border bg-surface p-1.5 shadow-lg"
      >
        {options.map((destination, index) => {
          const place = placeFor(destination.city)
          return (
            <li
              key={destination.city}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault() // keep the focus in the input
                pick(destination.city)
              }}
              onMouseEnter={() => setActive(index)}
              className={cn('flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5', index === active && 'bg-surface-2')}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
                <MapPin aria-hidden className="size-4" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-bold text-fg">{destination.city}</span>
                <span className="truncate text-xs text-muted">
                  {[destination.department, t('search.hotels', { count: destination.properties_count })].filter(Boolean).join(' · ')}
                </span>
              </span>
              {place && (
                <span className="num shrink-0 text-xs font-semibold text-muted">
                  {t('place.altitude', { altitude: formatNumber(place.altitude, lang, 0) })} · {t(`place.floors.${thermalFloor(place.altitude)}`)}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
