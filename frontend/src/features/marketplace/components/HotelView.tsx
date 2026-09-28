import { Check, Globe, Mail, MapPin, Phone, SearchX, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useOffers, useProperty, type Amenity, type Offer, type PropertyDetail, type Via } from '../api'
import { checkoutHref } from '../lib/links'
import { parseStay, stayApiParams, stayParams, type Stay } from '../lib/search-params'
import { withQuantity, type SelectionItem } from '../lib/selection'
import { tr } from '../lib/text'
import { AmenityIcon } from './AmenityIcon'
import { PlaceFacts } from './Cards'
import { Gallery } from './Gallery'
import { PolicyLine, RoomTypeCard } from './RoomTypeCard'
import { SearchBar } from './SearchBar'
import { MobileSelectionBar, SelectionSummary } from './SelectionSummary'
import { Stars } from './Stars'

const AMENITY_ORDER = ['property', 'room', 'bathroom', 'accessibility', 'view']
const WINDOW_ERRORS = ['too_soon', 'too_far', 'stay_too_long', 'invalid_dates', 'validation_error']

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`)
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function Section({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id ?? title}-title`} className="scroll-mt-24 border-t border-border pt-8">
      <h2 id={`${id ?? title}-title`} className="text-2xl font-extrabold tracking-[-0.03em] text-fg">
        {title}
      </h2>
      <div className="mt-5">{children}</div>
    </section>
  )
}

function groupAmenities(amenities: Amenity[]): [string, Amenity[]][] {
  const groups = new Map<string, Amenity[]>()
  for (const amenity of amenities) groups.set(amenity.category, [...(groups.get(amenity.category) ?? []), amenity])
  return [...groups.entries()].sort(([a], [b]) => AMENITY_ORDER.indexOf(a) - AMENITY_ORDER.indexOf(b))
}

interface HotelViewProps {
  slug: string
  via: Via
  /** The booking engine draws its own branded hero; the marketplace shows breadcrumb, gallery and title. */
  hero?: (detail: PropertyDetail) => ReactNode
  /** Where the "not found" state sends the guest. */
  notFound?: ReactNode
}

/**
 * The public hotel page, shared by the marketplace (`/hotel/:slug`) and the booking engine (`/h/:slug`): stay,
 * rooms with their rates for that stay, what the hotel offers, its policies and where it is.
 */
export function HotelView({ slug, via, hero, notFound }: HotelViewProps) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const [params, setParams] = useSearchParams()
  const stay = useMemo(() => parseStay(params), [params])
  const promo = (params.get('promo') ?? '').trim().toUpperCase()
  const detail = useProperty(slug, via)
  const hasDates = Boolean(stay.checkin && stay.checkout)
  const offersParams = useMemo(() => ({ ...stayApiParams(stay), via, promo_code: promo || undefined }), [stay, via, promo])
  const offers = useOffers(slug, offersParams, hasDates && detail.isSuccess)
  const [promoDraft, setPromoDraft] = useState(promo)

  // The selection belongs to one stay: a new search starts it again.
  const selectionKey = JSON.stringify(offersParams)
  const [selection, setSelection] = useState<{ key: string; items: SelectionItem[] }>({ key: selectionKey, items: [] })
  const items = selection.key === selectionKey ? selection.items : []

  if (detail.isPending) return <LoadingState className="min-h-[60vh]" />
  if (detail.isError) {
    if (isApiError(detail.error) && detail.error.status === 404) {
      return (
        notFound ?? (
          <EmptyState
            icon={SearchX}
            title={t('hotel.notFoundTitle')}
            description={t('hotel.notFoundBody')}
            className="min-h-[60vh] justify-center"
            action={
              <Button asChild>
                <Link to="/search">{t('hotel.backToSearch')}</Link>
              </Button>
            }
          />
        )
      )
    }
    return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} className="min-h-[60vh] justify-center" />
  }

  const hotel = detail.data
  const offerList: Offer[] = offers.data?.offers ?? []
  const appliedPromo = offers.data?.promo?.applied ? offers.data.promo.code : ''
  const toCheckout = checkoutHref(slug, stay, items, appliedPromo, via)
  const taxExempt = Boolean(offers.data?.tax_exempt)

  function search(next: Stay) {
    const query: Record<string, string> = stayParams(next)
    const code = promoDraft.trim().toUpperCase()
    if (code) query.promo = code
    setParams(new URLSearchParams(query), { replace: false, preventScrollReset: true })
  }

  function setQuantity(offer: Offer, quantity: number) {
    setSelection({ key: selectionKey, items: withQuantity(items, offer.room_type_id, offer.rate_plan_id, quantity) })
  }

  function offersError(): string {
    const error = offers.error
    if (isApiError(error) && WINDOW_ERRORS.includes(error.code)) {
      const data = error.data ?? {}
      if (error.code === 'too_soon') return t('hotel.errors.too_soon', { date: formatDate(String(data.earliest_checkin ?? ''), undefined, lang) })
      if (error.code === 'too_far') return t('hotel.errors.too_far', { date: formatDate(String(data.latest_checkin ?? ''), undefined, lang) })
      if (error.code === 'stay_too_long') return t('hotel.errors.stay_too_long', { count: Number(data.max_nights ?? hotel.booking.max_nights) })
      return t('hotel.errors.invalid_dates')
    }
    return errorMessage(error, t)
  }

  const policies = hotel.policies
  const houseRules = tr(hotel.house_rules, lang)
  const description = tr(hotel.description, lang)
  const tagline = tr(hotel.tagline, lang)

  return (
    <div className={cn('mx-auto w-full max-w-6xl px-4 pb-24 sm:px-6', !hero && 'pt-6')}>
      {hero ? (
        hero(hotel)
      ) : (
        <>
          <nav aria-label={t('hotel.breadcrumb')} className="mb-4 text-sm text-muted">
            <ol className="flex flex-wrap items-center gap-1.5">
              <li>
                <Link to="/" className="hover:text-fg hover:underline">
                  {t('hotel.home')}
                </Link>
              </li>
              <li aria-hidden>/</li>
              <li>
                <Link to={`/search?city=${encodeURIComponent(hotel.city)}&${new URLSearchParams(stayParams(stay))}`} className="hover:text-fg hover:underline">
                  {hotel.city}
                </Link>
              </li>
              <li aria-hidden>/</li>
              <li aria-current="page" className="font-semibold text-fg">
                {hotel.name}
              </li>
            </ol>
          </nav>
          <Gallery photos={hotel.photos} name={hotel.name} />
          <header className="mt-7">
            <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-muted">
              {t(`common:propertyTypes.${hotel.property_type}`, { defaultValue: hotel.property_type })}
              <Stars count={hotel.star_rating} />
            </p>
            <h1 className="mt-2 text-4xl leading-[1.02] font-extrabold tracking-[-0.04em] text-fg sm:text-5xl">{hotel.name}</h1>
            <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-muted">
              <MapPin aria-hidden className="size-4 text-accent" />
              {[hotel.neighborhood, hotel.city, hotel.department].filter(Boolean).join(', ')}
              <span aria-hidden>·</span>
              <PlaceFacts city={hotel.city} />
            </p>
            {tagline && <p className="mt-4 max-w-2xl text-lg leading-relaxed text-fg/85">{tagline}</p>}
          </header>
        </>
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-12">
        <aside aria-label={t('hotel.stay.title')} className="lg:order-2">
          <div className="grid gap-5 lg:sticky lg:top-24">
            <div className="rounded-2xl border border-border bg-surface-2/60 p-4">
              <h2 className="mb-3 text-base font-bold text-fg">{t('hotel.stay.title')}</h2>
              <SearchBar
                variant="panel"
                value={{ city: '', stay }}
                onSubmit={({ stay: next }) => search(next)}
                min={hotel.booking.earliest_checkin}
                max={addDays(hotel.booking.latest_checkin, hotel.booking.max_nights)}
                submitLabel={t('hotel.stay.submit')}
              >
                {hotel.booking.show_promo_field && (
                  <label className="grid gap-1 rounded-lg border border-border bg-surface px-3 py-2 focus-within:border-accent">
                    <span className="text-[12px] font-semibold text-muted">{t('hotel.stay.promo')}</span>
                    <Input
                      value={promoDraft}
                      onChange={(event) => setPromoDraft(event.target.value.toUpperCase())}
                      placeholder={t('hotel.stay.promoPlaceholder')}
                      className="h-auto border-0 p-0 text-[15px] font-semibold uppercase shadow-none placeholder:font-medium placeholder:normal-case focus-visible:ring-0"
                      autoComplete="off"
                    />
                  </label>
                )}
              </SearchBar>
              {offers.data?.promo && (
                <p role="status" className={cn('mt-3 text-sm font-semibold', offers.data.promo.applied ? 'text-success-ink' : 'text-danger-ink')}>
                  {offers.data.promo.applied
                    ? t('hotel.stay.promoApplied', { code: offers.data.promo.code })
                    : t('hotel.stay.promoInvalid', { code: offers.data.promo.code })}
                </p>
              )}
            </div>
            <div className="hidden lg:block" role="complementary" aria-label={t('hotel.summary.title')}>
              <SelectionSummary
                items={items}
                offers={offerList}
                currency={hotel.currency}
                taxExempt={taxExempt}
                checkoutHref={toCheckout}
                onRemove={(item) => setSelection({ key: selectionKey, items: withQuantity(items, item.roomTypeId, item.ratePlanId, 0) })}
              />
            </div>
          </div>
        </aside>

        <div className="grid min-w-0 gap-12 lg:order-1">
          <section id="rooms" aria-labelledby="rooms-title" className="scroll-mt-24">
            <h2 id="rooms-title" className="text-2xl font-extrabold tracking-[-0.03em] text-fg">
              {t('hotel.rooms.title')}
            </h2>
            {!hasDates ? (
              <p className="mt-2 text-muted">{t('hotel.rooms.pickDates')}</p>
            ) : offers.isError ? (
              <p role="alert" className="mt-3 rounded-xl border border-warning/40 bg-warning-soft px-4 py-3 text-sm font-medium text-warning-ink">
                {offersError()}
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">{taxExempt ? t('hotel.rooms.taxExemptNote') : t('hotel.rooms.taxNote')}</p>
            )}
            {hasDates && offers.isSuccess && offerList.length === 0 && (
              <div className="mt-4 rounded-2xl border border-border bg-surface px-5 py-6">
                <p className="font-bold text-fg">{t('hotel.rooms.noneTitle')}</p>
                <p className="mt-1 text-sm text-muted">{t('hotel.rooms.noneBody')}</p>
              </div>
            )}
            <div className={cn('mt-5 grid gap-4 transition-opacity', offers.isPlaceholderData && 'opacity-60')}>
              {hasDates && offers.isPending
                ? hotel.room_types.map((roomType) => <Skeleton key={roomType.id} className="h-64 rounded-2xl" />)
                : hotel.room_types.map((roomType) => (
                    <RoomTypeCard
                      key={roomType.id}
                      roomType={roomType}
                      offers={hasDates && offers.isSuccess ? offerList.filter((offer) => offer.room_type_id === roomType.id) : null}
                      allOffers={offerList}
                      items={items}
                      nights={offers.data?.nights ?? 0}
                      currency={hotel.currency}
                      onQuantity={setQuantity}
                    />
                  ))}
            </div>
          </section>

          {(description || hotel.highlights.length > 0) && (
            <Section id="about" title={t('hotel.about')}>
              {description && <p className="max-w-2xl leading-relaxed whitespace-pre-line text-fg/90">{description}</p>}
              {hotel.highlights.length > 0 && (
                <>
                  <h3 className="mt-6 text-sm font-bold text-fg">{t('hotel.highlights')}</h3>
                  <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                    {hotel.highlights.map((highlight, index) => (
                      <li key={index} className="flex items-start gap-2 text-fg/90">
                        <Check aria-hidden className="mt-1 size-4 shrink-0 text-accent" />
                        {tr(highlight, lang)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Section>
          )}

          {hotel.amenities.length > 0 && (
            <Section id="amenities" title={t('hotel.amenities')}>
              <div className="grid gap-6 sm:grid-cols-2">
                {groupAmenities(hotel.amenities).map(([category, amenities]) => (
                  <div key={category}>
                    <h3 className="text-sm font-bold text-fg">{t(`hotel.amenityCategories.${category}`, { defaultValue: category })}</h3>
                    <ul className="mt-2 grid gap-1.5">
                      {amenities.map((amenity) => (
                        <li key={amenity.code} className="flex items-center gap-2.5 text-sm text-fg/90">
                          <AmenityIcon name={amenity.icon} aria-hidden className="size-4 text-muted" />
                          {tr(amenity.name, lang)}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </Section>
          )}

          <Section id="policies" title={t('hotel.policies.title')}>
            <div className="grid gap-8 sm:grid-cols-2">
              <div>
                <h3 className="text-sm font-bold text-fg">{t('hotel.policies.schedule')}</h3>
                <ul className="mt-2 grid gap-1 text-sm text-fg/90">
                  {hotel.check_in_time && <li>{t('hotel.policies.checkin', { time: hotel.check_in_time })}</li>}
                  {hotel.check_out_time && <li>{t('hotel.policies.checkout', { time: hotel.check_out_time })}</li>}
                  <li>{t('hotel.policies.minAge', { age: policies.min_checkin_age })}</li>
                </ul>
                <ul className="mt-4 grid gap-1.5 text-sm">
                  {(
                    [
                      [policies.pets_allowed, 'petsYes', 'petsNo'],
                      [policies.children_allowed, 'childrenYes', 'childrenNo'],
                      [policies.smoking_allowed, 'smokingYes', 'smokingNo'],
                      [policies.events_allowed, 'eventsYes', 'eventsNo'],
                    ] as const
                  ).map(([allowed, yes, no]) => (
                    <li key={yes} className="flex items-center gap-2 text-fg/90">
                      {allowed ? <Check aria-hidden className="size-4 text-success" /> : <X aria-hidden className="size-4 text-muted" />}
                      {t(`hotel.policies.${allowed ? yes : no}`)}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-bold text-fg">{t('hotel.policies.cancellation')}</h3>
                <ul className="mt-2 grid gap-3">
                  {hotel.cancellation_policies.map((policy) => (
                    <li key={policy.id ?? tr(policy.name, lang)}>
                      <p className="text-xs font-semibold text-muted">{tr(policy.name, lang)}</p>
                      <PolicyLine policy={policy} className="mt-0.5" />
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            {houseRules && (
              <div className="mt-8">
                <h3 className="text-sm font-bold text-fg">{t('hotel.policies.rules')}</h3>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed whitespace-pre-line text-fg/90">{houseRules}</p>
              </div>
            )}
          </Section>

          <Section id="location" title={t('hotel.location.title')}>
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="text-fg/90">
                <p className="font-semibold text-fg">{hotel.address}</p>
                <p className="text-sm text-muted">{[hotel.neighborhood, hotel.city, hotel.department].filter(Boolean).join(', ')}</p>
                <p className="mt-2 text-sm text-muted">
                  <PlaceFacts city={hotel.city} />
                </p>
                {hotel.rnt_number && <p className="mt-3 text-xs text-subtle">{t('hotel.location.rnt', { number: hotel.rnt_number })}</p>}
              </div>
              {(hotel.phone || hotel.email || hotel.website) && (
                <div>
                  <h3 className="text-sm font-bold text-fg">{t('hotel.location.contact')}</h3>
                  <ul className="mt-2 grid gap-1.5 text-sm">
                    {hotel.phone && (
                      <li>
                        <a href={`tel:${hotel.phone.replace(/\s+/g, '')}`} className="inline-flex items-center gap-2 text-fg hover:underline">
                          <Phone aria-hidden className="size-4 text-muted" />
                          {hotel.phone}
                        </a>
                      </li>
                    )}
                    {hotel.email && (
                      <li>
                        <a href={`mailto:${hotel.email}`} className="inline-flex items-center gap-2 text-fg hover:underline">
                          <Mail aria-hidden className="size-4 text-muted" />
                          {hotel.email}
                        </a>
                      </li>
                    )}
                    {hotel.website && (
                      <li>
                        <a href={hotel.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-fg hover:underline">
                          <Globe aria-hidden className="size-4 text-muted" />
                          {hotel.website.replace(/^https?:\/\//, '')}
                        </a>
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          </Section>
        </div>
      </div>

      <MobileSelectionBar items={items} offers={offerList} currency={hotel.currency} checkoutHref={toCheckout} />
    </div>
  )
}
