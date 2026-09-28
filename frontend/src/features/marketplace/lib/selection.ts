/**
 * The rooms a guest picks on the hotel page travel to the checkout in the URL:
 * `items=<room type>:<rate plan>:<quantity>,…`.
 */

export interface SelectionItem {
  roomTypeId: string
  ratePlanId: string
  quantity: number
}

/** The parts of an offer the selection needs (a subset of the API offer). */
export interface SelectableOffer {
  room_type_id: string
  rate_plan_id: string
  available_units: number
  /** Units one booking of this offer takes: 1 room, or one dorm bed per guest. */
  units_needed: number
  total: string
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const sameOffer = (item: SelectionItem, roomTypeId: string, ratePlanId: string) =>
  item.roomTypeId === roomTypeId && item.ratePlanId === ratePlanId

export function serializeItems(items: SelectionItem[]): string {
  return items.map((item) => `${item.roomTypeId}:${item.ratePlanId}:${item.quantity}`).join(',')
}

/** Reads `items` from the URL, skipping malformed entries and merging repeated offers. */
export function parseItems(raw: string | null | undefined): SelectionItem[] {
  if (!raw) return []
  let items: SelectionItem[] = []
  for (const part of raw.split(',')) {
    const [roomTypeId = '', ratePlanId = '', quantityRaw = '', ...rest] = part.trim().split(':')
    if (rest.length || !UUID.test(roomTypeId) || !UUID.test(ratePlanId) || !/^\d+$/.test(quantityRaw)) continue
    const quantity = Number(quantityRaw)
    if (quantity <= 0) continue
    const current = items.find((item) => sameOffer(item, roomTypeId, ratePlanId))?.quantity ?? 0
    items = withQuantity(items, roomTypeId, ratePlanId, current + quantity)
  }
  return items
}

/** Sets the quantity of an offer (0 removes it), keeping the order of the other items. */
export function withQuantity(items: SelectionItem[], roomTypeId: string, ratePlanId: string, quantity: number): SelectionItem[] {
  const exists = items.some((item) => sameOffer(item, roomTypeId, ratePlanId))
  if (quantity <= 0) return items.filter((item) => !sameOffer(item, roomTypeId, ratePlanId))
  if (!exists) return [...items, { roomTypeId, ratePlanId, quantity }]
  return items.map((item) => (sameOffer(item, roomTypeId, ratePlanId) ? { ...item, quantity } : item))
}

/**
 * How many of this offer can still be chosen: the units of its room type are shared by every plan of that room
 * type, so what other plans already took is not available (the offer's own quantity does not count).
 */
export function quantityLeft(offer: SelectableOffer, items: SelectionItem[], offers: SelectableOffer[]): number {
  const taken = items.reduce((sum, item) => {
    if (item.roomTypeId !== offer.room_type_id || item.ratePlanId === offer.rate_plan_id) return sum
    const other = offers.find((candidate) => candidate.room_type_id === item.roomTypeId && candidate.rate_plan_id === item.ratePlanId)
    return sum + item.quantity * (other?.units_needed ?? 1)
  }, 0)
  const needed = Math.max(1, offer.units_needed)
  return Math.max(0, Math.floor((offer.available_units - taken) / needed))
}

export interface SelectionSummary {
  total: number
  /** Chosen quantities (rooms, or bed groups for dorms). */
  rooms: number
  lines: number
}

/** Total of the chosen offers that are still available. */
export function selectionSummary(items: SelectionItem[], offers: SelectableOffer[]): SelectionSummary {
  return items.reduce<SelectionSummary>(
    (summary, item) => {
      const offer = offers.find((candidate) => candidate.room_type_id === item.roomTypeId && candidate.rate_plan_id === item.ratePlanId)
      if (!offer) return summary
      return {
        total: summary.total + Number(offer.total) * item.quantity,
        rooms: summary.rooms + item.quantity,
        lines: summary.lines + 1,
      }
    },
    { total: 0, rooms: 0, lines: 0 },
  )
}
