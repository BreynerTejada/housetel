import { MessageCircleWarning } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// Owner: C6. ⌘K palette: jump to the threads waiting for an answer (the inbox and the simulator are already
// listed as pages).
export const commands: CommandItem[] = [
  {
    id: 'messaging.unread',
    group: 'navigation',
    labelKey: 'messaging:commands.unread',
    icon: MessageCircleWarning,
    keywords: ['bandeja', 'inbox', 'mensajes', 'messages', 'whatsapp', 'correo', 'email', 'sin leer', 'unread'],
    permission: 'messaging.view',
    perform: ({ navigate }) => navigate('/app/inbox?view=unread'),
  },
]
