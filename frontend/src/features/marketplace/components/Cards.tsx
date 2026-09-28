import { ArrowRight, ImageOff, MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Amenity, Destination, PropertyCard } from '../api'
import { placeFor, thermalFloor } from '../lib/places'
import { tr } from '../lib/text'
import { AmenityIcon } from './AmenityIcon'
import { Stars } from './Stars'

const SCARCE = 3

export function Photo({ src, alt = '', className }: { src: string | null | undefined; alt?: string; className?: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-surface-2', className)}>
      {src ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.03]"
        />
      ) : (
        <div className="grid size-full place-items-center text-subtle">
          <ImageOff aria-hidden className="size-6" />
        </div>
      )}
    </div>
  )
}

export function AmenityChip({ amenity, className }: { amenity: Amenity; className?: string }) {
  const { i18n } = useTranslation()
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium text-fg', className)}>
      <AmenityIcon name={amenity.icon} aria-hidden className="size-3.5 text-muted" />
      {tr(amenity.name, i18n.language)}
    </span>
  )
}

/** "2.640 m · Frío" for a city we know, or nothing. */
export function PlaceFacts({ city, className }: { city: string; className?: string }) {
  const { t, i18n } = useTranslation('marketplace')
  const place = placeFor(city)
  if (!place) return null
  return (
    <span className={cn('num', className)}>
      {t('place.altitude', { altitude: formatNumber(place.altitude, normalizeLang(i18n.language), 0) })} ·{' '}
      {t(`place.climate.${thermalFloor(place.altitude)}`)}
    </span>
  )
}

export function DestinationCard({ destination, href }: { destination: Destination; href: string }) {
  const { t } = useTranslation('marketplace')
  return (
    <Link to={href} className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-4 focus-visible:ring-offset-bg">
      <Photo src={destination.cover_photo} className="aspect-[4/3] rounded-xl" />
      <div className="mt-3 flex items-baseline justify-between gap-3">
        <h3 className="text-lg font-bold text-fg">{destination.city}</h3>
        <span className="text-sm font-semibold text-muted">{t('search.hotels', { count: destination.properties_count })}</span>
      </div>
      <p className="text-sm text-muted">
        {destination.department}
        {placeFor(destination.city) && (
          <>
            {' · '}
            <PlaceFacts city={destination.city} />
          </>
        )}
      </p>
    </Link>
  )
}

/** A hotel on the home page: photo, name and where it is. */
export function HotelTile({ hotel, href }: { hotel: PropertyCard; href: string }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const tagline = tr(hotel.tagline, i18n.language)
  return (
    <article className="group relative flex flex-col">
      <Photo src={hotel.photo} className="aspect-[5/4] rounded-xl" />
      <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-muted">
        {t(`common:propertyTypes.${hotel.property_type}`, { defaultValue: hotel.property_type })}
        <Stars count={hotel.star_rating} />
      </p>
      <h3 className="mt-1 text-lg leading-snug font-bold text-fg">
        <Link to={href} className="outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:underline">
          {hotel.name}
        </Link>
      </h3>
      <p className="flex items-center gap-1 text-sm text-muted">
        <MapPin aria-hidden className="size-3.5 shrink-0" />
        {[hotel.neighborhood, hotel.city].filter(Boolean).join(', ')}
      </p>
      {tagline && <p className="mt-2 line-clamp-2 text-sm text-fg/85">{tagline}</p>}
    </article>
  )
}

/** A search result: photo, the facts that decide, and the cheapest offer for the stay. */
export function ResultCard({ hotel, href, nights }: { hotel: PropertyCard; href: string; nights: number }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = i18n.language
  const offer = hotel.offer
  const tagline = tr(hotel.tagline, lang)
  const left = offer ? Math.floor(offer.available_units / Math.max(1, offer.units_needed)) : 0
  return (
    <article className="group relative grid gap-4 rounded-2xl border border-border bg-surface p-3 shadow-xs transition-shadow hover:shadow-md sm:grid-cols-[14rem_minmax(0,1fr)] lg:grid-cols-[16rem_minmax(0,1fr)_13rem]">
      <Photo src={hotel.photo} className="aspect-[4/3] rounded-xl sm:aspect-auto sm:h-full sm:min-h-44" />
      <div className="min-w-0 py-1 sm:pr-2">
        <p className="flex flex-wrap items-center gap-2 text-xs font-semibold text-muted">
          {t(`common:propertyTypes.${hotel.property_type}`, { defaultValue: hotel.property_type })}
          <Stars count={hotel.star_rating} />
        </p>
        <h2 className="mt-1 text-xl leading-snug font-bold tracking-[-0.02em] text-fg">
          <Link to={href} className="outline-none after:absolute after:inset-0 after:rounded-2xl hover:underline focus-visible:underline">
            {hotel.name}
          </Link>
        </h2>
        <p className="mt-1 flex items-center gap-1 text-sm text-muted">
          <MapPin aria-hidden className="size-3.5 shrink-0" />
          {[hotel.neighborhood, hotel.city].filter(Boolean).join(', ')}
        </p>
        {tagline && <p className="mt-2.5 line-clamp-2 text-sm text-fg/85">{tagline}</p>}
        {hotel.amenities.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label={t('results.card.amenities')}>
            {hotel.amenities.slice(0, 4).map((amenity) => (
              <li key={amenity.code}>
                <AmenityChip amenity={amenity} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col justify-end gap-1 border-t border-border pt-3 sm:col-span-2 lg:col-span-1 lg:items-end lg:border-t-0 lg:border-l lg:pt-1 lg:pl-5 lg:text-right">
        {offer ? (
          <>
            <p className="text-xs text-muted">
              {tr(offer.room_type.name, lang)} · {t(`meal.${offer.rate_plan.meal_plan}`)}
            </p>
            {left > 0 && left <= SCARCE && (
              <Badge tone="warning" className="lg:self-end">
                {t('results.card.left', { count: left })}
              </Badge>
            )}
            <p className="mt-1 text-xs font-semibold text-muted">{t('results.card.from')}</p>
            <p className="text-[1.65rem] leading-none font-extrabold tracking-[-0.03em] text-fg">
              <MoneyText value={offer.per_night} currency={offer.currency} className="[font-variant-numeric:normal]" />
            </p>
            <p className="text-xs text-muted">{t('results.card.perNight')}</p>
            <p className="text-xs text-muted">
              {t('results.card.totalFor', { nights: t('common:date.nights', { count: nights }) })}{' '}
              <MoneyText value={offer.total} currency={offer.currency} className="font-semibold text-fg" />
            </p>
            <Button asChild variant="primary" className="relative z-10 mt-3 w-full lg:w-auto">
              <Link to={href}>
                {t('results.card.choose')}
                <ArrowRight aria-hidden />
              </Link>
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-muted">{t('results.card.pickDates')}</p>
            <Button asChild className="relative z-10 mt-2 w-full lg:w-auto">
              <Link to={href}>{t('results.card.view')}</Link>
            </Button>
          </>
        )}
      </div>
    </article>
  )
}
