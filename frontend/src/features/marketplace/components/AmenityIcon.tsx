import { createElement } from 'react'
import type { LucideProps } from 'lucide-react'
import { amenityIcon } from '@/features/inventory/lib/amenityIcons'

/** The lucide icon of an amenity (by its kebab-case name; unknown names get a neutral sparkle). */
export function AmenityIcon({ name, ...props }: LucideProps & { name: string | undefined }) {
  return createElement(amenityIcon(name), props)
}
