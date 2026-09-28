import type { GuestTab } from '@/app/extensions'
import { GuestMessagesTab } from './components/MessagesTab'

// Owner: C6. The guest profile (B3) renders these tabs through `useGuestTabs()`.
export const guestTabs: GuestTab[] = [
  { id: 'messages', labelKey: 'messaging:tab.label', order: 20, permission: 'messaging.view', Component: GuestMessagesTab },
]
