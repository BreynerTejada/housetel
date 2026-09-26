import { Inbox, MessageCircle, Smartphone } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `messaging` feature (plan §E). Owner: C6.
export const nav: NavItem[] = [
  { id: 'inbox', section: 'operations', labelKey: 'messaging:nav.inbox', icon: Inbox, path: '/app/inbox', permission: 'messaging.view', order: 50 },
  { id: 'waSim', section: 'tools', labelKey: 'messaging:nav.waSim', icon: Smartphone, path: '/app/simulators/whatsapp', permission: 'messaging.send', order: 40 },
  { id: 'settingsMessaging', section: 'settings', labelKey: 'messaging:nav.settingsMessaging', icon: MessageCircle, path: '/app/settings/messaging', permission: 'messaging.templates', order: 100, descriptionKey: 'messaging:nav.settingsMessagingHint' },
]
