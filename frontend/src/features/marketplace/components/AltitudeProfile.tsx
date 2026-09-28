import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Destination } from '../api'
import { placeFor, profileLayout, THERMAL_FLOORS, thermalFloor, type ThermalFloor } from '../lib/places'

const MAX_POINTS = 6
/** Scale up to the páramo, so the four floors are always in view. */
const MIN_CEILING = 4000
/** Width each destination needs for its label; narrower screens scroll the chart sideways. */
const COLUMN_REM = 6.75

interface ProfilePoint extends Destination {
  altitude: number
  floor: ThermalFloor
}

/** The destinations we can place (known altitude), the ones with more hotels first. */
function profilePoints(destinations: Destination[]): ProfilePoint[] {
  return destinations
    .flatMap((destination) => {
      const place = placeFor(destination.city)
      return place ? [{ ...destination, altitude: place.altitude, floor: thermalFloor(place.altitude) }] : []
    })
    .sort((a, b) => b.properties_count - a.properties_count)
    .slice(0, MAX_POINTS)
}

// The plot box leaves room above for the labels of the highest point and below for the sea line.
const PLOT_VARS = { '--top': '5.75rem', '--base': '2.25rem' } as CSSProperties
/** Position in the chart box: sea level at `--base` from the bottom, the ceiling at `--top` from the top. */
const chartBottom = (fraction: number) => `calc(var(--base) + (100% - var(--base) - var(--top)) * ${fraction})`
const chartHeight = (fraction: number) => `calc((100% - var(--base) - var(--top)) * ${fraction})`
/** Same scale inside a destination's link, whose box starts at sea level. */
const linkOffset = (fraction: number) => `calc((100% - var(--top)) * ${fraction})`

interface AltitudeProfileProps {
  destinations: Destination[]
  /** Link of a destination (the page keeps the current stay in it). */
  hrefFor: (city: string) => string
  className?: string
}

/**
 * The marketplace's signature: the destinations standing at their altitude over Colombia's thermal floors
 * ("pisos térmicos"), from the Caribbean to the páramo. Each stem is a thin bar from sea level (an honest
 * magnitude), labeled with the city and its altitude, and links to that destination's hotels. The destination
 * cards below repeat every value, so nothing is only readable here.
 */
export function AltitudeProfile({ destinations, hrefFor, className }: AltitudeProfileProps) {
  const { t, i18n } = useTranslation('marketplace')
  const lang = normalizeLang(i18n.language)
  const points = profilePoints(destinations)
  if (points.length === 0) return null

  const layout = profileLayout(points, { minCeiling: MIN_CEILING })
  const bands = THERMAL_FLOORS.filter((band) => band.from < layout.ceiling)
  const meters = (value: number) => formatNumber(value, lang, 0)

  return (
    <div className={className}>
      <div className="-mx-4 overflow-x-auto px-4 [scrollbar-width:thin] sm:mx-0 sm:px-0">
        <div
          className="relative h-[19rem] [--gutter:0rem] sm:h-[22rem] sm:[--gutter:6.5rem]"
          style={{ ...PLOT_VARS, minWidth: `calc(var(--gutter) + ${points.length * COLUMN_REM}rem)` }}
        >
          {bands.map((band, index) => {
            const to = Math.min(band.to ?? layout.ceiling, layout.ceiling)
            return (
              <div
                key={band.floor}
                aria-hidden
                className={cn('absolute inset-x-0 border-t border-border', index % 2 === 1 && 'bg-surface-2/60')}
                style={{ bottom: chartBottom(band.from / layout.ceiling), height: chartHeight((to - band.from) / layout.ceiling) }}
              >
                <span className="absolute top-2 left-0 hidden w-24 text-[11px] leading-tight sm:block">
                  <span className="block font-bold text-fg">{t(`place.floors.${band.floor}`)}</span>
                  <span className="block text-muted">{t(`place.temps.${band.floor}`)}</span>
                </span>
                {band.from > 0 && (
                  <span className="num absolute -top-2 right-0 hidden bg-bg pl-1.5 text-[11px] leading-4 text-subtle sm:block">
                    {t('place.altitude', { altitude: meters(band.from) })}
                  </span>
                )}
              </div>
            )
          })}
          <div aria-hidden className="absolute inset-x-0 border-t border-border-strong" style={{ bottom: 'var(--base)' }}>
            <span className="absolute top-2 left-0 text-[11px] font-semibold text-muted">{t('home.profile.seaLevel')}</span>
          </div>

          <ul aria-label={t('home.profile.chartLabel')} className="absolute inset-y-0 right-0 left-(--gutter)">
            {layout.points.map((point) => (
              <li key={point.city} className="absolute inset-y-0 w-0" style={{ left: `${point.x}%` }}>
                <Link
                  to={hrefFor(point.city)}
                  aria-label={t('home.profile.point', {
                    city: point.city,
                    altitude: meters(point.altitude),
                    floor: t(`place.floors.${point.floor}`).toLowerCase(),
                    hotels: t('search.hotels', { count: point.properties_count }),
                  })}
                  className="group absolute top-0 -left-[3.3rem] w-[6.6rem] rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                  style={{ bottom: 'var(--base)' }}
                >
                  <span
                    aria-hidden
                    className="absolute bottom-0 left-1/2 w-0.5 -translate-x-1/2 bg-accent transition-[width] duration-200 group-hover:w-1"
                    style={{ height: linkOffset(point.y / 100) }}
                  />
                  <span
                    aria-hidden
                    className="absolute left-1/2 size-3 -translate-x-1/2 translate-y-1/2 rounded-full bg-accent shadow-[0_0_0_3px_var(--bg)] transition-transform duration-200 group-hover:scale-125"
                    style={{ bottom: linkOffset(point.y / 100) }}
                  />
                  <span aria-hidden className="absolute inset-x-0 flex flex-col items-center pb-4 text-center" style={{ bottom: linkOffset(point.y / 100) }}>
                    <span className="text-[1.7rem] leading-none font-extrabold tracking-[-0.045em] text-fg sm:text-[2.4rem]">
                      {meters(point.altitude)}
                      <span className="ml-0.5 text-sm font-bold tracking-normal text-muted sm:text-base">m</span>
                    </span>
                    <span className="mt-1.5 text-sm font-bold text-fg decoration-accent decoration-2 underline-offset-4 group-hover:underline">
                      {point.city}
                    </span>
                    <span className="text-xs text-muted">{t('search.hotels', { count: point.properties_count })}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {/* the floors as a legend on phones (wider screens label them inside the chart) */}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:hidden">
        {bands.map((band) => (
          <div key={band.floor}>
            <dt className="font-bold text-fg">{t(`place.floors.${band.floor}`)}</dt>
            <dd className="text-muted">
              {t(`place.range.${band.floor}`)} · {t(`place.temps.${band.floor}`)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
