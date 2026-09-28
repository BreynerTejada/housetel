import type { TopbarItem } from '@/app/extensions'
import { InboxTopbarButton } from './components/InboxTopbarButton'

// Owner: C6. Inbox button with the threads waiting for an answer (topbar of the staff shell).
export const topbarItems: TopbarItem[] = [{ id: 'messaging-inbox', order: 20, permission: 'messaging.view', Component: InboxTopbarButton }]
