/** Links between the public pages. The stay (dates and party) travels in every link. */
import type { Via } from '../api'
import { DEFAULT_SEARCH, searchParams, stayParams, type Stay } from './search-params'
import { serializeItems, type SelectionItem } from './selection'

const query = (params: Record<string, string>) => {
  const search = new URLSearchParams(params).toString()
  return search ? `?${search}` : ''
}

export function cityHref(city: string, stay?: Stay): string {
  return `/search?${searchParams({ ...DEFAULT_SEARCH, ...stay, city })}`
}

/** Hotel page on the marketplace (`/hotel/:slug`) or the hotel's own booking engine (`/h/:slug`). */
export function hotelHref(slug: string, stay: Stay | null, via: Via = 'marketplace'): string {
  const base = via === 'booking_engine' ? `/h/${encodeURIComponent(slug)}` : `/hotel/${encodeURIComponent(slug)}`
  return `${base}${stay ? query(stayParams(stay)) : ''}`
}

export function checkoutHref(slug: string, stay: Stay, items: SelectionItem[], promo: string, via: Via = 'marketplace'): string {
  const base = via === 'booking_engine' ? `/h/${encodeURIComponent(slug)}/book` : `/book/${encodeURIComponent(slug)}`
  const params: Record<string, string> = { ...stayParams(stay), items: serializeItems(items) }
  if (promo) params.promo = promo
  return `${base}${query(params)}`
}
