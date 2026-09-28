import { ArrowRight, KeyRound, Landmark, ReceiptText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { LogoMark } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDestinations, useSearch } from '../api'
import { AltitudeProfile } from '../components/AltitudeProfile'
import { DestinationCard, HotelTile } from '../components/Cards'
import { SearchBar, type SearchValue } from '../components/SearchBar'
import { cityHref } from '../lib/links'
import { DEFAULT_SEARCH, DEFAULT_STAY, searchParams } from '../lib/search-params'

const FEATURED_QUERY = { adults: 2 }
const FEATURED_COUNT = 6
const EMPTY_SEARCH: SearchValue = { city: '', stay: DEFAULT_STAY }

const FACTS: { key: string; icon: LucideIcon }[] = [
  { key: 'price', icon: ReceiptText },
  { key: 'tax', icon: Landmark },
  { key: 'checkin', icon: KeyRound },
]

/**
 * `/` — the marketplace home. The search comes first (it is the page's job); right below, the destinations
 * stand at their altitude over Colombia's thermal floors, the one image nobody else has.
 */
export default function HomePage() {
  const { t } = useTranslation('marketplace')
  const navigate = useNavigate()
  const destinations = useDestinations()
  const featured = useSearch(FEATURED_QUERY)
  const list = destinations.data ?? []
  const hotels = (featured.data?.results ?? []).slice(0, FEATURED_COUNT)

  function search({ city, stay }: SearchValue) {
    navigate(`/search?${searchParams({ ...DEFAULT_SEARCH, ...stay, city })}`)
  }

  return (
    <div className="pb-20">
      <section className="mx-auto w-full max-w-6xl px-4 pt-12 sm:px-6 sm:pt-20">
        <p className="eyebrow text-accent-ink">{t('home.eyebrow')}</p>
        <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-end">
          <h1 className="max-w-[11ch] text-[clamp(2.9rem,8.2vw,6.1rem)] leading-[0.93] font-extrabold tracking-[-0.05em] text-fg">
            {t('home.title')}
          </h1>
          <p className="max-w-md pb-2 text-lg leading-relaxed text-muted">{t('home.subtitle')}</p>
        </div>
        <SearchBar className="mt-10" value={EMPTY_SEARCH} onSubmit={search} destinations={list} />
        <p className="mt-4 text-sm text-muted">{t('home.searchFacts')}</p>
      </section>

      {list.length > 0 && (
        <section aria-labelledby="profile-title" className="mx-auto mt-20 w-full max-w-6xl px-4 sm:mt-28 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-[19rem_minmax(0,1fr)] lg:gap-14">
            <div className="lg:pt-6">
              <p className="eyebrow">{t('home.profile.eyebrow')}</p>
              <h2 id="profile-title" className="mt-3 text-4xl leading-[1.02] font-extrabold tracking-[-0.04em] text-fg sm:text-5xl">
                {t('home.profile.title')}
              </h2>
              <p className="mt-5 leading-relaxed text-muted">{t('home.profile.body')}</p>
            </div>
            <AltitudeProfile destinations={list} hrefFor={(city) => cityHref(city)} />
          </div>
        </section>
      )}

      <section aria-labelledby="destinations-title" className="mx-auto mt-20 w-full max-w-6xl px-4 sm:px-6">
        <h2 id="destinations-title" className="text-2xl font-extrabold tracking-[-0.03em] text-fg sm:text-3xl">
          {t('home.destinations.title')}
        </h2>
        <div className="mt-6 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {destinations.isPending
            ? Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="aspect-[4/3] rounded-xl" />)
            : list.map((destination) => <DestinationCard key={destination.city} destination={destination} href={cityHref(destination.city)} />)}
        </div>
      </section>

      {(featured.isPending || hotels.length > 0) && (
        <section aria-labelledby="featured-title" className="mx-auto mt-24 w-full max-w-6xl px-4 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 id="featured-title" className="text-2xl font-extrabold tracking-[-0.03em] text-fg sm:text-3xl">
                {t('home.featured.title')}
              </h2>
              <p className="mt-2 text-muted">{t('home.featured.subtitle')}</p>
            </div>
            <Link to="/search" className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent-ink hover:underline">
              {t('home.featured.all')}
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          <div className="mt-8 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {featured.isPending
              ? Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="aspect-[5/4] rounded-xl" />)
              : hotels.map((hotel) => <HotelTile key={hotel.slug} hotel={hotel} href={`/hotel/${hotel.slug}`} />)}
          </div>
        </section>
      )}

      <section aria-labelledby="facts-title" className="mx-auto mt-24 w-full max-w-6xl px-4 sm:px-6">
        <h2 id="facts-title" className="text-2xl font-extrabold tracking-[-0.03em] text-fg sm:text-3xl">
          {t('home.facts.title')}
        </h2>
        <ul className="mt-8 grid gap-8 border-t border-border pt-8 md:grid-cols-3">
          {FACTS.map(({ key, icon: Icon }) => (
            <li key={key} className="max-w-sm">
              <Icon aria-hidden className="size-5 text-accent" />
              <h3 className="mt-3 text-base font-bold text-fg">{t(`home.facts.${key}.title`)}</h3>
              <p className="mt-1.5 text-[15px] leading-relaxed text-muted">{t(`home.facts.${key}.body`)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mx-auto mt-24 w-full max-w-6xl px-4 sm:px-6">
        <div className="flex flex-col items-start gap-6 rounded-2xl border border-border bg-surface p-6 sm:flex-row sm:items-center sm:p-8">
          <LogoMark className="size-11" />
          <div className="max-w-xl flex-1">
            <h2 className="text-xl font-bold text-fg">{t('home.hotels.title')}</h2>
            <p className="mt-1.5 text-muted">{t('home.hotels.body')}</p>
          </div>
          <Button asChild size="lg" variant="secondary">
            <Link to="/signup">{t('home.hotels.cta')}</Link>
          </Button>
        </div>
      </section>
    </div>
  )
}
