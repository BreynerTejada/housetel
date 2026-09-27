/**
 * Inventory API (backend `/api/v1/inventory/`, see docs/integration-notes/B1-inventory.md).
 * Types mirror the serializers; hooks wrap TanStack Query. Mutations invalidate `inventoryKeys.all`.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '@/lib/api'

// ---- Types ---------------------------------------------------------------------------------------

export interface I18nText {
  es?: string
  en?: string
}

export type RoomTypeKind = 'private' | 'dorm'
export type HousekeepingStatus = 'clean' | 'dirty' | 'inspected' | 'out_of_service'
export const HOUSEKEEPING_STATUSES: HousekeepingStatus[] = ['clean', 'dirty', 'inspected', 'out_of_service']

export const BED_CONFIG_TYPES = ['single', 'twin', 'double', 'queen', 'king', 'bunk', 'sofa_bed', 'crib'] as const
export type BedConfigType = (typeof BED_CONFIG_TYPES)[number]
export interface BedConfig {
  type: BedConfigType
  count: number
}

export type AmenityCategory = 'room' | 'bathroom' | 'property' | 'accessibility' | 'view'
export const AMENITY_CATEGORIES: AmenityCategory[] = ['room', 'bathroom', 'view', 'accessibility', 'property']
export interface Amenity {
  id: string
  code: string
  name: I18nText
  icon: string
  category: AmenityCategory
  is_global: boolean
}

/** Option values of select fields may be numbers (the API accepts text or numbers). */
export type CustomValue = string | number | boolean | (string | number)[] | null
export type CustomValues = Record<string, CustomValue>

/** Category attributes a room may override (backend ROOM_OVERRIDABLE_FIELDS, in its order). */
export const OVERRIDABLE_FIELDS = [
  'name',
  'description',
  'base_occupancy',
  'max_adults',
  'max_children',
  'max_occupancy',
  'beds',
  'size_m2',
  'view',
  'smoking_allowed',
  'accessible',
  'housekeeping_minutes',
] as const
export type OverridableField = (typeof OVERRIDABLE_FIELDS)[number]

export interface CategoryAttributes {
  name: I18nText
  description: I18nText
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  beds: BedConfig[]
  size_m2: string | null
  view: string
  smoking_allowed: boolean
  accessible: boolean
  housekeeping_minutes: number
}
export type RoomOverrides = Partial<CategoryAttributes>

export interface RoomType extends CategoryAttributes {
  id: string
  code: string
  kind: RoomTypeKind
  amenities: string[]
  color: string
  sort_order: number
  is_active: boolean
  custom_values: CustomValues
  rooms_count: number
  active_rooms_count: number
  beds_count: number
  units_count: number
  photos_count: number
  cover_photo: string | null
  created_at: string
  updated_at: string
}

export interface EffectiveAttributes extends CategoryAttributes {
  room_id: string
  room_type_id: string
  number: string
  room_name: string
  floor: string
  building: string
  kind: RoomTypeKind
  amenities: string[]
  amenities_added: string[]
  amenities_removed: string[]
  custom_values: CustomValues
  overridden_fields: OverridableField[]
  overridden_custom_fields: string[]
}

export interface RoomEffective extends EffectiveAttributes {
  inherited: CategoryAttributes & { amenities: string[]; custom_values: CustomValues }
}

export interface ActiveBlock {
  id: string
  bed: string | null
  start_date: string
  end_date: string
  kind: BlockKind
  reason: string
}

export interface Room {
  id: string
  number: string
  name: string
  floor: string
  building: string
  room_type: string
  room_type_code: string
  room_type_name: I18nText
  kind: RoomTypeKind
  color: string
  overrides: RoomOverrides
  extra_amenities: string[]
  removed_amenities: string[]
  custom_values: CustomValues
  housekeeping_status: HousekeepingStatus
  is_active: boolean
  sort_order: number
  notes: string
  connecting_rooms: string[]
  beds_count: number
  active_beds_count: number
  effective: EffectiveAttributes
  overridden_fields: OverridableField[]
  active_block: ActiveBlock | null
  created_at: string
  updated_at: string
}

export type BedType = 'single' | 'bunk_top' | 'bunk_bottom' | 'double'
export interface Bed {
  id: string
  room: string
  label: string
  bed_type: BedType
  is_active: boolean
}

export interface Photo {
  id: string
  url: string
  caption: I18nText
  sort_order: number
  room_type: string | null
  created_at: string
}

export type CustomFieldTarget = 'room_type' | 'room' | 'guest' | 'reservation'
export const CUSTOM_FIELD_TARGETS: CustomFieldTarget[] = ['room_type', 'room', 'guest', 'reservation']
export type CustomFieldType = 'text' | 'number' | 'boolean' | 'select' | 'multiselect' | 'date'
export const CUSTOM_FIELD_TYPES: CustomFieldType[] = ['text', 'number', 'boolean', 'select', 'multiselect', 'date']
export interface CustomFieldOption {
  value: string | number
  label: I18nText
}
export interface CustomFieldDefinition {
  id: string
  applies_to: CustomFieldTarget
  key: string
  label: I18nText
  field_type: CustomFieldType
  options: CustomFieldOption[]
  required: boolean
  default_value: CustomValue
  show_in_marketplace: boolean
  sort_order: number
  scope: 'organization' | 'property'
}

export type BlockKind = 'out_of_order' | 'out_of_service' | 'maintenance' | 'owner_hold'
export const BLOCK_KINDS: BlockKind[] = ['out_of_order', 'out_of_service', 'maintenance', 'owner_hold']
export interface RoomBlock {
  id: string
  room: string
  room_number: string
  room_type: string
  bed: string | null
  bed_label: string | null
  start_date: string
  end_date: string
  kind: BlockKind
  reason: string
  created_by_name: string
  released_at: string | null
  is_active: boolean
  created_at: string
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface SummaryWarning {
  code: 'room_type_without_rooms' | 'dorm_room_without_beds' | string
  room_type_id?: string
  room_id?: string
  message: string
}

export interface InventorySummary {
  room_types: {
    id: string
    code: string
    name: I18nText
    kind: RoomTypeKind
    color: string
    is_active: boolean
    max_occupancy: number
    rooms: number
    active_rooms: number
    beds: number
    units: number
  }[]
  totals: { room_types: number; active_room_types: number; rooms: number; active_rooms: number; beds: number; units: number }
  housekeeping: Record<HousekeepingStatus, number>
  blocked_today: number
  warnings: SummaryWarning[]
  profile_missing: string[]
}

export interface PropertyPolicies {
  pets_allowed: boolean
  smoking_allowed: boolean
  children_allowed: boolean
  events_allowed: boolean
  min_checkin_age: number | null
}

export interface PropertyProfile {
  id: string
  name: string
  slug: string
  property_type: string
  status: string
  timezone: string
  currency: string
  business_date: string
  marketplace_listed: boolean
  description: I18nText
  address: string
  city: string
  department: string
  country: string
  latitude: string | null
  longitude: string | null
  phone: string
  email: string
  website: string
  rnt_number: string
  nit: string
  legal_name: string
  star_rating: number | null
  check_in_time: string
  check_out_time: string
  default_language: 'es' | 'en'
  languages: string[]
  house_rules: I18nText
  policies: PropertyPolicies
  amenities: string[]
  branding: { primary_color: string; logo: string }
}

// ---- Query keys and hooks -----------------------------------------------------------------------

export type RoomFilters = Partial<Record<'room_type' | 'floor' | 'housekeeping_status' | 'is_active' | 'search', string>>
export type BlockFilters = Partial<Record<'room' | 'bed' | 'active' | 'current' | 'kind' | 'start' | 'end' | 'page', string>>

export const inventoryKeys = {
  all: ['inventory'] as const,
  property: () => [...inventoryKeys.all, 'property'] as const,
  amenities: () => [...inventoryKeys.all, 'amenities'] as const,
  roomTypes: () => [...inventoryKeys.all, 'room-types'] as const,
  roomType: (id: string) => [...inventoryKeys.all, 'room-types', id] as const,
  photos: (roomTypeId: string | null) => [...inventoryKeys.all, 'photos', roomTypeId ?? 'property'] as const,
  rooms: (filters: RoomFilters = {}) => [...inventoryKeys.all, 'rooms', filters] as const,
  room: (id: string) => [...inventoryKeys.all, 'room', id] as const,
  effective: (id: string) => [...inventoryKeys.all, 'room', id, 'effective'] as const,
  beds: (roomId: string) => [...inventoryKeys.all, 'room', roomId, 'beds'] as const,
  customFields: (appliesTo?: CustomFieldTarget) => [...inventoryKeys.all, 'custom-fields', appliesTo ?? 'all'] as const,
  blocks: (filters: BlockFilters = {}) => [...inventoryKeys.all, 'blocks', filters] as const,
  summary: () => [...inventoryKeys.all, 'summary'] as const,
}

export const photosPath = (roomTypeId: string | null) =>
  roomTypeId ? `/inventory/room-types/${roomTypeId}/photos/` : '/inventory/property/photos/'

export function usePropertyProfile() {
  return useQuery({ queryKey: inventoryKeys.property(), queryFn: () => api.get<PropertyProfile>('/inventory/property/') })
}

export function useAmenities() {
  return useQuery({ queryKey: inventoryKeys.amenities(), queryFn: () => api.get<Amenity[]>('/inventory/amenities/') })
}

export function useRoomTypes() {
  return useQuery({ queryKey: inventoryKeys.roomTypes(), queryFn: () => api.get<RoomType[]>('/inventory/room-types/') })
}

export function useRoomType(id: string | undefined) {
  return useQuery({
    queryKey: inventoryKeys.roomType(id ?? ''),
    queryFn: () => api.get<RoomType>(`/inventory/room-types/${id}/`),
    enabled: Boolean(id),
  })
}

export function usePhotos(roomTypeId: string | null, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.photos(roomTypeId),
    queryFn: () => api.get<Photo[]>(photosPath(roomTypeId)),
    enabled,
  })
}

export function useRooms(filters: RoomFilters = {}) {
  return useQuery({
    queryKey: inventoryKeys.rooms(filters),
    queryFn: () => api.get<Room[]>('/inventory/rooms/', { params: filters }),
  })
}

export function useRoom(id: string | undefined) {
  return useQuery({
    queryKey: inventoryKeys.room(id ?? ''),
    queryFn: () => api.get<Room>(`/inventory/rooms/${id}/`),
    enabled: Boolean(id),
  })
}

export function useRoomEffective(id: string | undefined) {
  return useQuery({
    queryKey: inventoryKeys.effective(id ?? ''),
    queryFn: () => api.get<RoomEffective>(`/inventory/rooms/${id}/effective/`),
    enabled: Boolean(id),
  })
}

export function useBeds(roomId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.beds(roomId ?? ''),
    queryFn: () => api.get<Bed[]>(`/inventory/rooms/${roomId}/beds/`),
    enabled: Boolean(roomId) && enabled,
  })
}

export function useCustomFields(appliesTo?: CustomFieldTarget) {
  return useQuery({
    queryKey: inventoryKeys.customFields(appliesTo),
    queryFn: () => api.get<CustomFieldDefinition[]>('/inventory/custom-fields/', { params: { applies_to: appliesTo } }),
  })
}

export function useBlocks(filters: BlockFilters = {}, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.blocks(filters),
    queryFn: () => api.get<Page<RoomBlock>>('/inventory/blocks/', { params: { page_size: 100, ...filters } }),
    enabled,
  })
}

export function useInventorySummary() {
  return useQuery({ queryKey: inventoryKeys.summary(), queryFn: () => api.get<InventorySummary>('/inventory/summary/') })
}

/** Refetch everything inventory-related after a write (lists, counts, summary, effective values). */
export function useInvalidateInventory() {
  const queryClient = useQueryClient()
  return useCallback(() => queryClient.invalidateQueries({ queryKey: inventoryKeys.all }), [queryClient])
}
