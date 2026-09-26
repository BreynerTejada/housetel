import { MessagesSquare, Sparkles, WandSparkles } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `ai` feature (plan §E). Owner: C9.
export const nav: NavItem[] = [
  { id: 'onboarding', section: 'tools', labelKey: 'ai:nav.onboarding', icon: WandSparkles, path: '/app/onboarding', permission: 'ai.onboarding', order: 10 },
  { id: 'chatbot', section: 'settings', labelKey: 'ai:nav.chatbot', icon: MessagesSquare, path: '/app/settings/chatbot', permission: 'ai.settings', order: 180, descriptionKey: 'ai:nav.chatbotHint' },
  { id: 'aiSettings', section: 'settings', labelKey: 'ai:nav.aiSettings', icon: Sparkles, path: '/app/settings/ai', permission: 'ai.settings', order: 190, descriptionKey: 'ai:nav.aiSettingsHint' },
]
