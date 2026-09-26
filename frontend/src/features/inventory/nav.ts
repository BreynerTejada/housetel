import { BedDouble, DoorOpen, Hotel, SlidersHorizontal } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `inventory` feature (plan §E). Owner: B1.
export const nav: NavItem[] = [
  { id: 'property', section: 'settings', labelKey: 'inventory:nav.property', icon: Hotel, path: '/app/settings/property', permission: 'inventory.manage', order: 10, descriptionKey: 'inventory:nav.propertyHint' },
  { id: 'roomTypes', section: 'settings', labelKey: 'inventory:nav.roomTypes', icon: BedDouble, path: '/app/settings/room-types', permission: 'inventory.view', order: 20, descriptionKey: 'inventory:nav.roomTypesHint' },
  { id: 'rooms', section: 'settings', labelKey: 'inventory:nav.rooms', icon: DoorOpen, path: '/app/settings/rooms', permission: 'inventory.view', order: 30, descriptionKey: 'inventory:nav.roomsHint' },
  { id: 'customFields', section: 'settings', labelKey: 'inventory:nav.customFields', icon: SlidersHorizontal, path: '/app/settings/custom-fields', permission: 'inventory.manage', order: 40, descriptionKey: 'inventory:nav.customFieldsHint' },
]
