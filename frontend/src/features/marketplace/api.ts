/**
 * Marketplace and booking engine API (backend `apps/marketplace`): public endpoints under
 * `/api/v1/public/marketplace/` (no session) and the staff settings under `/api/v1/marketplace/`.
 * Types mirror the real payloads (see docs/integration-notes/C4-marketplace.md).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, publicApi, type Query } from '@/lib/api'

export type I18nText = Partial<Record<'es' | 'en', string>>
export type Via = 'marketplace' | 'booking_engine'
export type MealPlan = 'room_only' | 'breakfast' | 'half_board' | 'full_board' | 'all_inclusive'
export type PaymentOption = 'pay_now' | 'pay_at_hotel'
export type ChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'

export interface Amenity {
  code: string
  name: I18nText
  /** lucide icon name in kebab-case */
  icon: string
  category: string
}

export interface Destination {
  city: string
  department: string
  properties_count: number
  cover_photo: string | null
}

export interface CheapestOffer {
  room_type: { id: string; code: string; name: I18nText }
  rate_plan: { id: string; code: string; name: I18nText; meal_plan: MealPlan }
  total: string
  per_night: string
  currency: string
  available_units: number
  units_needed: number
  taxes_included: boolean
}

export interface PropertyCard {
  slug: string
  name: string
  property_type: string
  star_rating: number | null
  city: string
  department: string
  neighborhood: string
  tagline: I18nText
  highlights: I18nText[]
  photo: string | null
  photos: string[]
  amenities: Amenity[]
  currency: string
  /** Cheapest bookable offer for the searched stay (null without dates). */
  offer: CheapestOffer | null
}

export interface Facet<T> {
  value: T
  count: number
}

export interface SearchResponse {
  count: number
  city: string
  checkin: string | null
  checkout: string | null
  nights: number
  adults: number
  children: number
  results: PropertyCard[]
  facets: { types: Facet<string>[]; stars: Facet<number>[]; amenities: (Amenity & { count: number })[] }
}

export interface Photo {
  id: string
  url: string
  caption: I18nText
}

export interface CancellationPolicy {
  id?: string
  name: I18nText
  description: I18nText
  non_refundable: boolean
  free_until_hours_before: number
  penalty_type: 'first_night' | 'percent' | 'full'
  penalty_value: string
}

export interface RoomFeature {
  key: string
  label: I18nText
  field_type: string
  value: unknown
  display: I18nText[] | null
}

export interface Bed {
  type: string
  count: number
}

export interface RoomTypeInfo {
  id: string
  code: string
  name: I18nText
  description: I18nText
  kind: 'private' | 'dorm'
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  beds: Bed[]
  size_m2: string | null
  size_m2_range: [string, string] | null
  views: string[]
  smoking_allowed: boolean
  accessible: boolean
  amenities: Amenity[]
  photos: Photo[]
  features: RoomFeature[]
  units_count: number
}

export interface ExtraInfo {
  id: string
  code: string
  name: I18nText
  price: string
  charge_type: ChargeType
  tax_rate: string | null
  tax_included: boolean
}

export interface BookingWindow {
  earliest_checkin: string
  latest_checkin: string
  max_nights: number
}

export interface Brand {
  primary_color: string
  logo: string
}

export interface HousePolicies {
  pets_allowed: boolean
  smoking_allowed: boolean
  children_allowed: boolean
  events_allowed: boolean
  min_checkin_age: number
}

export interface PropertyDetail {
  slug: string
  name: string
  property_type: string
  star_rating: number | null
  city: string
  department: string
  neighborhood: string
  tagline: I18nText
  highlights: I18nText[]
  photo: string | null
  currency: string
  description: I18nText
  address: string
  country: string
  latitude: string | null
  longitude: string | null
  phone: string
  email: string
  website: string
  rnt_number: string
  check_in_time: string | null
  check_out_time: string | null
  house_rules: I18nText
  policies: HousePolicies
  languages: string[]
  amenities: Amenity[]
  photos: Photo[]
  hero_image: string | null
  room_types: RoomTypeInfo[]
  cancellation_policies: CancellationPolicy[]
  extras: ExtraInfo[]
  headline: I18nText
  terms: I18nText
  booking: BookingWindow & {
    min_advance_hours: number
    max_advance_days: number
    show_promo_field: boolean
    online_payments: boolean
  }
  brand: Brand
  marketplace_listed: boolean
  booking_engine_enabled: boolean
  via: Via
}

export interface OfferQuoteNight {
  date: string
  base: string
  extra_adults: string
  extra_children: string
  discount: string
  total: string
}

export interface Offer {
  room_type_id: string
  rate_plan_id: string
  room_type: {
    id: string
    code: string
    name: I18nText
    kind: 'private' | 'dorm'
    max_adults: number
    max_children: number
    max_occupancy: number
    photo: string | null
  }
  rate_plan: {
    id: string
    code: string
    name: I18nText
    meal_plan: MealPlan
    deposit_percent: string
    requires_payment: boolean
    cancellation_policy: CancellationPolicy | null
  }
  available_units: number
  units_needed: number
  max_quantity: number
  quote: { nights: OfferQuoteNight[]; discount_total: string; promo_applied: string | null }
  net_total: string
  tax_total: string
  total: string
  per_night: string
  tax_exempt: boolean
  promo_applied: string | null
}

export interface OffersResponse {
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  currency: string
  tax_exempt: boolean
  online_payments: boolean
  promo: { code: string; applied: boolean } | null
  offers: Offer[]
}

export interface CheckoutItem {
  room_type_id: string
  rate_plan_id: string
  quantity: number
  adults: number
  children: number
  children_ages: number[]
}

export interface CheckoutRequest {
  property_slug: string
  via: Via
  checkin: string
  checkout: string
  items: CheckoutItem[]
  /** `quantity: null` lets the hotel's rule decide (per person-night…). */
  extras: { extra_id: string; quantity: number | null }[]
  promo_code: string
  payment_option: PaymentOption
  guest: { nationality: string; country_of_residence: string }
}

export interface CheckoutQuote {
  property_slug: string
  via: Via
  checkin: string
  checkout: string
  nights: number
  currency: string
  tax_exempt: boolean
  items: {
    room_type_id: string
    rate_plan_id: string
    room_type_name: I18nText
    room_type_kind: 'private' | 'dorm'
    rate_plan_name: I18nText
    meal_plan: MealPlan
    quantity: number
    adults: number
    children: number
    units: number
    net: string
    tax: string
    total: string
    discount: string
    deposit: string
    deposit_percent: string
    cancellation_policy: CancellationPolicy | null
  }[]
  extras: {
    extra_id: string
    code: string
    name: I18nText
    charge_type: ChargeType
    quantity: number
    unit_price: string
    net: string
    tax: string
    total: string
    tax_exempt: boolean
  }[]
  lodging_total: string
  extras_total: string
  tax_total: string
  discount_total: string
  total: string
  deposit_total: string
  requires_payment: boolean
  due_now: Record<PaymentOption, string>
  payment_option: PaymentOption
  amount_due_now: string
  promo: { code: string; applied: boolean } | null
  online_payments: boolean
}

export interface GuestData {
  first_name: string
  last_name: string
  email: string
  phone: string
  nationality: string
  country_of_residence: string
  document_type: string
  document_number: string
  data_processing_consent: boolean
  marketing_consent: boolean
}

export interface BookingRequest extends Omit<CheckoutRequest, 'guest'> {
  guest: GuestData
  special_requests: string
  eta: string | null
  language: 'es' | 'en'
}

export interface BookingResult {
  reservation_code: string
  status: 'tentative' | 'confirmed'
  via: Via
  currency: string
  total: string
  amount_due_now: string
  payment: { checkout_url: string; reference: string; amount: string; expires_at: string | null } | null
  hold_expires_at: string | null
  portal_url: string
  confirmation_path: string
}

export type ReservationStatus = 'tentative' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show'
export type LinkStatus = 'created' | 'pending' | 'approved' | 'declined' | 'expired' | 'error'

export interface BookingStatus {
  code: string
  status: ReservationStatus
  via: Via
  property: {
    slug: string
    name: string
    city: string
    address: string
    phone: string
    email: string
    timezone: string
    check_in_time: string | null
    check_out_time: string | null
    primary_color: string
    logo: string
  }
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  currency: string
  booker: { first_name: string; last_name: string; email: string }
  rooms: {
    room_type_name: I18nText
    room_type_kind: 'private' | 'dorm'
    rate_plan_name: I18nText
    meal_plan: MealPlan
    units: number
    adults: number
    children: number
    total: string
  }[]
  extras: { description: string; quantity: number; total: string }[]
  total: string
  paid: string
  balance: string
  tax_exempt: boolean
  cancellation_policy: CancellationPolicy | null
  hold_expires_at: string | null
  special_requests: string
  eta: string | null
  payment: { reference: string; status: LinkStatus; amount: string; checkout_url: string | null; expires_at: string | null } | null
  portal_url: string
  confirmation_path: string
  created_at: string
}

export interface EngineConfig {
  slug: string
  name: string
  city: string
  department: string
  property_type: string
  star_rating: number | null
  address: string
  phone: string
  email: string
  currency: string
  enabled: boolean
  primary_color: string
  logo: string
  hero_image: string | null
  headline: I18nText
  show_promo_field: boolean
  terms: I18nText
  booking: BookingWindow & { online_payments: boolean }
  languages: string[]
}

// ---- Staff settings --------------------------------------------------------------------------------

export interface EngineSettings {
  enabled: boolean
  primary_color: string
  logo: string
  logo_is_custom: boolean
  hero_image: string | null
  headline: I18nText
  show_promo_field: boolean
  allowed_rate_plans: string[]
  min_advance_hours: number
  max_advance_days: number
  terms: I18nText
  rate_plans: { id: string; code: string; name: I18nText; kind: 'base' | 'derived'; channels: string[]; sells_on_engine: boolean }[]
  public_url: string
  embed_url: string
  property: { name: string; slug: string; city: string }
}

export type EngineSettingsInput = Partial<
  Pick<
    EngineSettings,
    'enabled' | 'primary_color' | 'headline' | 'show_promo_field' | 'allowed_rate_plans' | 'min_advance_hours' | 'max_advance_days' | 'terms'
  >
>

export interface ListingSettings {
  marketplace_listed: boolean
  tagline: I18nText
  highlights: I18nText[]
  neighborhood: string
  featured_photo_ids: string[]
  photos: (Photo & { room_type: { id: string; code: string; name: I18nText } | null })[]
  description: I18nText
  name: string
  city: string
  star_rating: number | null
  property_type: string
  public_url: string
}

export type ListingSettingsInput = Partial<Pick<ListingSettings, 'marketplace_listed' | 'tagline' | 'highlights' | 'neighborhood' | 'featured_photo_ids'>>

export interface EmbedSnippet {
  engine_url: string
  embed_url: string
  iframe: string
  button: string
}

export interface PromoCode {
  id: string
  code: string
  discount_type: 'percent' | 'amount'
  value: string
  valid_from: string | null
  valid_to: string | null
  stay_from: string | null
  stay_to: string | null
  is_active: boolean
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---- Fetchers --------------------------------------------------------------------------------------

const PUBLIC = '/marketplace'

export const getDestinations = () => publicApi.get<Destination[]>(`${PUBLIC}/destinations/`)
export const getSearch = (params: Query, signal?: AbortSignal) => publicApi.get<SearchResponse>(`${PUBLIC}/search/`, { params, signal })
export const getProperty = (slug: string, via: Via) =>
  publicApi.get<PropertyDetail>(`${PUBLIC}/properties/${encodeURIComponent(slug)}/`, { params: { via } })
export const getOffers = (slug: string, params: Query, signal?: AbortSignal) =>
  publicApi.get<OffersResponse>(`${PUBLIC}/properties/${encodeURIComponent(slug)}/offers/`, { params, signal })
export const getEngineConfig = (slug: string) => publicApi.get<EngineConfig>(`${PUBLIC}/properties/${encodeURIComponent(slug)}/booking-engine/`)
export const postCheckoutQuote = (body: CheckoutRequest, signal?: AbortSignal) =>
  publicApi.post<CheckoutQuote>(`${PUBLIC}/checkout/quote/`, body, { signal })
export const postBooking = (body: BookingRequest) => publicApi.post<BookingResult>(`${PUBLIC}/bookings/`, body)
export const getBookingStatus = (code: string, email: string) =>
  publicApi.get<BookingStatus>(`${PUBLIC}/bookings/${encodeURIComponent(code)}/`, { params: { email } })

export const getEngineSettings = () => api.get<EngineSettings>('/marketplace/booking-engine/')
export const patchEngineSettings = (body: EngineSettingsInput) => api.patch<EngineSettings>('/marketplace/booking-engine/', body)
export const uploadEngineImage = (kind: 'logo' | 'hero', file: File) => {
  const formData = new FormData()
  formData.append('image', file)
  return api.post<EngineSettings>(`/marketplace/booking-engine/${kind}/`, undefined, { formData })
}
export const deleteEngineImage = (kind: 'logo' | 'hero') => api.delete<EngineSettings>(`/marketplace/booking-engine/${kind}/`)
export const getListingSettings = () => api.get<ListingSettings>('/marketplace/listing/')
export const patchListingSettings = (body: ListingSettingsInput) => api.patch<ListingSettings>('/marketplace/listing/', body)
export const getEmbedSnippet = () => api.get<EmbedSnippet>('/marketplace/embed-snippet/')
export const getActivePromoCodes = () =>
  api.get<Page<PromoCode>>('/rates/promo-codes/', { params: { is_active: true, page_size: 50 } })

// ---- Query keys and hooks --------------------------------------------------------------------------

export const marketplaceKeys = {
  all: ['marketplace'] as const,
  destinations: () => ['marketplace', 'destinations'] as const,
  search: (params: Query) => ['marketplace', 'search', params] as const,
  property: (slug: string, via: Via) => ['marketplace', 'property', slug, via] as const,
  offers: (slug: string, params: Query) => ['marketplace', 'offers', slug, params] as const,
  engine: (slug: string) => ['marketplace', 'engine', slug] as const,
  quote: (body: CheckoutRequest) => ['marketplace', 'quote', body] as const,
  booking: (code: string, email: string) => ['marketplace', 'booking', code.toUpperCase(), email.toLowerCase()] as const,
  engineSettings: ['marketplace', 'settings', 'engine'] as const,
  listingSettings: ['marketplace', 'settings', 'listing'] as const,
  embedSnippet: ['marketplace', 'settings', 'embed'] as const,
  promoCodes: ['marketplace', 'settings', 'promo-codes'] as const,
}

export function useDestinations() {
  return useQuery({ queryKey: marketplaceKeys.destinations(), queryFn: getDestinations, staleTime: 5 * 60_000 })
}

export function useSearch(params: Query) {
  return useQuery({
    queryKey: marketplaceKeys.search(params),
    queryFn: ({ signal }) => getSearch(params, signal),
    placeholderData: keepPreviousData,
  })
}

export function useProperty(slug: string, via: Via) {
  return useQuery({ queryKey: marketplaceKeys.property(slug, via), queryFn: () => getProperty(slug, via), staleTime: 60_000 })
}

export function useOffers(slug: string, params: Query, enabled: boolean) {
  return useQuery({
    queryKey: marketplaceKeys.offers(slug, params),
    queryFn: ({ signal }) => getOffers(slug, params, signal),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useEngineConfig(slug: string) {
  return useQuery({ queryKey: marketplaceKeys.engine(slug), queryFn: () => getEngineConfig(slug), staleTime: 60_000 })
}

export function useCheckoutQuote(body: CheckoutRequest | null) {
  return useQuery({
    queryKey: body ? marketplaceKeys.quote(body) : ['marketplace', 'quote', 'idle'],
    queryFn: ({ signal }) => postCheckoutQuote(body!, signal),
    enabled: body !== null,
    placeholderData: keepPreviousData,
    // a quote that fails (no availability, invalid promo) is an answer, not a network hiccup
    retry: false,
  })
}

export function useBookingStatus(code: string, email: string | null) {
  return useQuery({
    queryKey: marketplaceKeys.booking(code, email ?? ''),
    queryFn: () => getBookingStatus(code, email!),
    enabled: Boolean(email),
    retry: false,
  })
}
