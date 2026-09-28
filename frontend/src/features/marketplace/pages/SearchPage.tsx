import { MapPinned, SearchX, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useDestinations, useSearch } from '../api'
import { PlaceFacts, ResultCard } from '../components/Cards'
import { FiltersPanel } from '../components/FiltersPanel'
import { SearchBar, type SearchValue } from '../components/SearchBar'
import { cityHref, hotelHref } from '../lib/links'
import { placeFor } from '../lib/places'
import { activeFilterCount, parseSearch, searchApiParams, searchParams, SORTS, type SearchSort, type SearchState } from '../lib/search-params'
import { guestsLabel } from '../lib/text'

const NO_FILTERS: Partial<SearchState> = { types: [], stars: [], amenities: [], minPrice: '', maxPrice: '' }

/** `/search` — hotels of a destination (or all), filtered and sorted; the whole state lives in the URL. */
export default function SearchPage() {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const [params, setParams] = useSearchParams()
  const state = useMemo(() => parseSearch(params), [params])
  const query = useMemo(() => searchApiParams(state), [state])
  const results = useSearch(query)
  const destinations = useDestinations()
  const [filtersOpen, setFiltersOpen] = useState(false)

  const data = results.data
  const filters = activeFilterCount(state)
  const hasDates = Boolean(state.checkin && state.checkout)
  const searchValue: SearchValue = { city: state.city, stay: state }
  const place = placeFor(state.city)
  const noHotelsInCity = Boolean(data && state.city && data.facets.types.length === 0)

  function update(patch: Partial<SearchState>) {
    setParams(searchParams({ ...state, ...patch }))
  }

  const filtersPanel = (
    <FiltersPanel state={state} facets={data?.facets} currency={data?.results[0]?.currency} onChange={update} />
  )

  return (
    <div className="pb-20">
      <div className="border-b border-border bg-surface-2/50">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 sm:px-6">
          <SearchBar
            variant="compact"
            value={searchValue}
            destinations={destinations.data ?? []}
            onSubmit={({ city, stay }) => update({ ...stay, city })}
          />
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl px-4 pt-8 sm:px-6 sm:pt-10">
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
          <div className="min-w-0">
            <h1 className="text-4xl leading-none font-extrabold tracking-[-0.04em] text-fg sm:text-5xl">{state.city || t('results.titleAll')}</h1>
            <p className="mt-3 text-sm text-muted">
              {place && (
                <>
                  {place.department} · <PlaceFacts city={state.city} />
                  {' · '}
                </>
              )}
              {data && <span className="font-semibold text-fg">{t('results.count', { count: data.count })}</span>}
            </p>
            <p className="mt-1 text-sm text-muted">
              {hasDates
                ? t('results.withDates', {
                    dates: formatDateRange(state.checkin, state.checkout, lang),
                    nights: t('common:date.nights', { count: data?.nights ?? 0 }),
                    guests: guestsLabel(state.adults, state.children, t),
                  })
                : t('results.noDates')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
              <SheetTrigger asChild>
                <Button className="lg:hidden">
                  <SlidersHorizontal aria-hidden />
                  {filters ? t('results.filtersActive', { count: filters }) : t('results.filters')}
                </Button>
              </SheetTrigger>
              <SheetContent side="bottom" className="lg:hidden">
                <SheetHeader>
                  <SheetTitle>{t('results.filters')}</SheetTitle>
                </SheetHeader>
                <SheetBody>{filtersPanel}</SheetBody>
                <SheetFooter className="justify-between">
                  {filters > 0 && (
                    <Button variant="ghost" onClick={() => update(NO_FILTERS)}>
                      {t('results.clearFilters')}
                    </Button>
                  )}
                  <Button variant="primary" onClick={() => setFiltersOpen(false)}>
                    {t('results.show', { count: data?.count ?? 0 })}
                  </Button>
                </SheetFooter>
              </SheetContent>
            </Sheet>
            <Select value={state.sort} onValueChange={(sort) => update({ sort: sort as SearchSort })}>
              <SelectTrigger aria-label={t('results.sort')} className="w-auto min-w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                {SORTS.map((sort) => (
                  <SelectItem key={sort} value={sort}>
                    {t(`results.sorts.${sort}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </header>

        <div className="mt-8 grid gap-10 lg:grid-cols-[15.5rem_minmax(0,1fr)]">
          <aside aria-label={t('results.filters')} className="hidden lg:block">
            <div className="sticky top-24">
              {filtersPanel}
              {filters > 0 && (
                <Button variant="ghost" size="sm" className="mt-4 -ml-3" onClick={() => update(NO_FILTERS)}>
                  {t('results.clearFilters')}
                </Button>
              )}
            </div>
          </aside>

          <section aria-busy={results.isFetching} aria-label={t('results.count', { count: data?.count ?? 0 })}>
            {results.isPending ? (
              <div className="grid gap-4">
                {Array.from({ length: 3 }, (_, index) => (
                  <Skeleton key={index} className="h-56 rounded-2xl" />
                ))}
              </div>
            ) : results.isError ? (
              <ErrorState error={results.error} onRetry={() => void results.refetch()} />
            ) : noHotelsInCity ? (
              <div className="rounded-2xl border border-border bg-surface px-6 py-10">
                <MapPinned aria-hidden className="size-6 text-accent" />
                <p className="mt-3 text-lg font-bold text-fg">{t('results.emptyCityTitle', { city: state.city })}</p>
                <p className="mt-1 text-muted">{t('results.emptyCityBody')}</p>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {(destinations.data ?? []).map((destination) => (
                    <li key={destination.city}>
                      <Button asChild size="sm">
                        <Link to={cityHref(destination.city, state)}>
                          {destination.city} · {t('search.hotels', { count: destination.properties_count })}
                        </Link>
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : data && data.results.length === 0 ? (
              <EmptyState
                icon={SearchX}
                title={t('results.emptyTitle')}
                description={t('results.emptyBody')}
                className="rounded-2xl border border-border bg-surface"
                action={
                  filters > 0 ? (
                    <Button onClick={() => update(NO_FILTERS)}>{t('results.clearFilters')}</Button>
                  ) : (
                    <Button asChild>
                      <Link to={`/search?${searchParams({ ...state, city: '' })}`}>{t('results.allDestinations')}</Link>
                    </Button>
                  )
                }
              />
            ) : (
              <ul className={cn('grid gap-4 transition-opacity', results.isPlaceholderData && 'opacity-60')}>
                {data?.results.map((hotel) => (
                  <li key={hotel.slug}>
                    <ResultCard hotel={hotel} href={hotelHref(hotel.slug, state)} nights={data.nights} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
