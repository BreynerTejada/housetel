import { UserPlus } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// ⌘K palette: open the "new guest" form from anywhere (the guests page opens it for `?new=1`).
export const commands: CommandItem[] = [
  {
    id: 'guests.new',
    group: 'actions',
    labelKey: 'guests:commands.new',
    icon: UserPlus,
    keywords: ['huésped', 'guest', 'cliente', 'crm'],
    permission: 'guests.manage',
    perform: ({ navigate }) => navigate('/app/guests?new=1'),
  },
]
