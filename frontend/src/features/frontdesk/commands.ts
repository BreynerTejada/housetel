import { DoorOpen, Plus, Search, UsersRound } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

/** A reservation code typed in the palette ("reserva ht-7k2m9q" → "HT-7K2M9Q"). */
const CODE = /\bht-?[a-z0-9]{3,}\b/i

// ⌘K palette (plan C1): start a reservation or a walk-in, or find a reservation by its code; groups (P3).
export const commands: CommandItem[] = [
  {
    id: 'frontdesk.newReservation',
    group: 'actions',
    labelKey: 'frontdesk:commands.newReservation',
    icon: Plus,
    keywords: ['reserva', 'booking', 'nueva', 'new'],
    permission: 'bookings.manage',
    perform: ({ navigate }) => navigate('/app/reservations/new'),
  },
  {
    id: 'frontdesk.walkIn',
    group: 'actions',
    labelKey: 'frontdesk:commands.walkIn',
    icon: DoorOpen,
    keywords: ['walk-in', 'llegada', 'arrival', 'ahora', 'now'],
    permission: 'bookings.manage',
    perform: ({ navigate }) => navigate('/app/reservations/new?walk_in=1'),
  },
  {
    id: 'frontdesk.groupReservation',
    group: 'actions',
    labelKey: 'frontdesk:commands.groupReservation',
    icon: UsersRound,
    keywords: ['grupo', 'group', 'boda', 'wedding', 'congreso', 'evento', 'event', 'cupo', 'allotment', 'varias', 'habitaciones'],
    permission: 'bookings.manage',
    perform: ({ navigate }) => navigate('/app/reservations/new?group_mode=1'),
  },
  {
    id: 'frontdesk.groups',
    group: 'actions',
    labelKey: 'frontdesk:commands.groups',
    icon: UsersRound,
    keywords: ['grupos', 'groups', 'rooming', 'cupos', 'allotments', 'bloqueos'],
    permission: 'bookings.view',
    perform: ({ navigate }) => navigate('/app/groups'),
  },
  {
    id: 'frontdesk.findReservation',
    group: 'actions',
    labelKey: 'frontdesk:commands.findReservation',
    icon: Search,
    keywords: ['buscar', 'search', 'código', 'code', 'reserva', 'HT'],
    permission: 'bookings.view',
    perform: ({ navigate, query }) => {
      const code = query ? CODE.exec(query)?.[0] : undefined
      navigate(code ? `/app/reservations?q=${encodeURIComponent(code.toUpperCase())}` : '/app/reservations?focus=search')
    },
  },
]
