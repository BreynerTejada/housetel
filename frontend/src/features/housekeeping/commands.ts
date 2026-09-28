import { Camera, ListChecks } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// ⌘K palette: the housekeeper's day and the damage report form (the maintenance page opens it for `?new=1`).
export const commands: CommandItem[] = [
  {
    id: 'housekeeping.mine',
    group: 'navigation',
    labelKey: 'housekeeping:commands.mine',
    icon: ListChecks,
    keywords: ['limpieza', 'camarera', 'habitaciones', 'housekeeping', 'rooms'],
    permission: 'housekeeping.work',
    perform: ({ navigate }) => navigate('/app/housekeeping/mine'),
  },
  {
    id: 'housekeeping.report',
    group: 'actions',
    labelKey: 'housekeeping:commands.report',
    icon: Camera,
    keywords: ['daño', 'mantenimiento', 'avería', 'damage', 'maintenance'],
    permission: 'housekeeping.work',
    perform: ({ navigate }) => navigate('/app/maintenance?new=1'),
  },
]
