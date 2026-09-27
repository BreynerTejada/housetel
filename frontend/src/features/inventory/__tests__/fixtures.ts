import type { Amenity, CustomFieldDefinition, EffectiveAttributes, Room, RoomEffective, RoomType } from '../api'

export const standardType: RoomType = {
  id: 'rt-dbl',
  code: 'DBL',
  name: { es: 'Estándar', en: 'Standard' },
  description: { es: 'Habitación colonial', en: 'Colonial room' },
  kind: 'private',
  base_occupancy: 2,
  max_adults: 2,
  max_children: 1,
  max_occupancy: 3,
  beds: [{ type: 'queen', count: 1 }],
  size_m2: '22.00',
  view: 'city',
  smoking_allowed: false,
  accessible: false,
  amenities: ['wifi'],
  color: '#4E6C88',
  housekeeping_minutes: 30,
  sort_order: 10,
  is_active: true,
  custom_values: { orientation: 'city' },
  rooms_count: 2,
  active_rooms_count: 2,
  beds_count: 0,
  units_count: 2,
  photos_count: 0,
  cover_photo: null,
  created_at: '2026-09-25T10:00:00-05:00',
  updated_at: '2026-09-25T10:00:00-05:00',
}

export const dormType: RoomType = {
  ...standardType,
  id: 'rt-d6',
  code: 'D6',
  name: { es: 'Dormitorio mixto 6 camas', en: '6-bed mixed dorm' },
  kind: 'dorm',
  base_occupancy: 1,
  max_adults: 1,
  max_children: 0,
  max_occupancy: 1,
  beds: [{ type: 'bunk', count: 3 }],
  color: '#B98A2E',
  sort_order: 20,
  units_count: 6,
  beds_count: 6,
  rooms_count: 1,
  active_rooms_count: 1,
}

export const amenities: Amenity[] = [
  { id: 'a1', code: 'wifi', name: { es: 'Wifi', en: 'Wi-Fi' }, icon: 'wifi', category: 'room', is_global: true },
  { id: 'a2', code: 'bathtub', name: { es: 'Bañera', en: 'Bathtub' }, icon: 'bath', category: 'bathroom', is_global: true },
]

export const orientationField: CustomFieldDefinition = {
  id: 'cf-orientation',
  applies_to: 'room_type',
  key: 'orientation',
  label: { es: 'Orientación', en: 'Orientation' },
  field_type: 'select',
  options: [
    { value: 'sea', label: { es: 'Mar', en: 'Sea' } },
    { value: 'city', label: { es: 'Ciudad', en: 'City' } },
  ],
  required: false,
  default_value: null,
  show_in_marketplace: true,
  sort_order: 20,
  scope: 'organization',
}

export const minibarField: CustomFieldDefinition = {
  id: 'cf-minibar',
  applies_to: 'room',
  key: 'minibar',
  label: { es: 'Minibar surtido', en: 'Stocked minibar' },
  field_type: 'boolean',
  options: [],
  required: false,
  default_value: false,
  show_in_marketplace: false,
  sort_order: 10,
  scope: 'organization',
}

function effectiveOf(roomType: RoomType, room: Pick<Room, 'id' | 'number' | 'name' | 'floor' | 'building' | 'overrides' | 'custom_values'>): EffectiveAttributes {
  const overrides = room.overrides
  const pick = <K extends keyof RoomType>(key: K) => (key in overrides ? (overrides as Record<string, unknown>)[key] : roomType[key])
  return {
    name: pick('name') as RoomType['name'],
    description: pick('description') as RoomType['description'],
    base_occupancy: pick('base_occupancy') as number,
    max_adults: pick('max_adults') as number,
    max_children: pick('max_children') as number,
    max_occupancy: pick('max_occupancy') as number,
    beds: pick('beds') as RoomType['beds'],
    size_m2: pick('size_m2') as string | null,
    view: pick('view') as string,
    smoking_allowed: pick('smoking_allowed') as boolean,
    accessible: pick('accessible') as boolean,
    housekeeping_minutes: pick('housekeeping_minutes') as number,
    room_id: room.id,
    room_type_id: roomType.id,
    number: room.number,
    room_name: room.name,
    floor: room.floor,
    building: room.building,
    kind: roomType.kind,
    amenities: roomType.amenities,
    amenities_added: [],
    amenities_removed: [],
    custom_values: { ...roomType.custom_values, ...room.custom_values },
    overridden_fields: Object.keys(overrides) as EffectiveAttributes['overridden_fields'],
    overridden_custom_fields: Object.keys(room.custom_values),
  }
}

export function makeRoom(overrides: Partial<Room> = {}, roomType: RoomType = standardType): Room {
  const base = {
    id: 'room-101',
    number: '101',
    name: '',
    floor: '1',
    building: '',
    overrides: {},
    custom_values: {},
    ...overrides,
  }
  return {
    room_type: roomType.id,
    room_type_code: roomType.code,
    room_type_name: roomType.name,
    kind: roomType.kind,
    color: roomType.color,
    extra_amenities: [],
    removed_amenities: [],
    housekeeping_status: 'clean',
    is_active: true,
    sort_order: 0,
    notes: '',
    connecting_rooms: [],
    beds_count: 0,
    active_beds_count: 0,
    active_block: null,
    created_at: '2026-09-25T10:00:00-05:00',
    updated_at: '2026-09-25T10:00:00-05:00',
    ...base,
    ...overrides,
    effective: effectiveOf(roomType, base),
    overridden_fields: Object.keys(base.overrides) as Room['overridden_fields'],
  }
}

export function effectiveResponse(room: Room, roomType: RoomType = standardType): RoomEffective {
  return {
    ...room.effective,
    inherited: {
      name: roomType.name,
      description: roomType.description,
      base_occupancy: roomType.base_occupancy,
      max_adults: roomType.max_adults,
      max_children: roomType.max_children,
      max_occupancy: roomType.max_occupancy,
      beds: roomType.beds,
      size_m2: roomType.size_m2,
      view: roomType.view,
      smoking_allowed: roomType.smoking_allowed,
      accessible: roomType.accessible,
      housekeeping_minutes: roomType.housekeeping_minutes,
      amenities: roomType.amenities,
      custom_values: roomType.custom_values,
    },
  }
}
