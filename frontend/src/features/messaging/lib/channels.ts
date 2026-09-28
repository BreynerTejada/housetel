import { Globe, Mail, MessageCircle, MessagesSquare, StickyNote, type LucideIcon } from 'lucide-react'
import type { MessageChannel } from '../api'

/**
 * Each channel keeps one color everywhere (chips, bubbles): WhatsApp → sage, email → slate, web chat →
 * sand, OTA → stone. Internal notes are sand "message slips" (see MessageBubble).
 */
export const CHANNEL_META: Record<MessageChannel, { icon: LucideIcon; chip: string; bubble: string }> = {
  whatsapp: { icon: MessageCircle, chip: 'bg-success-soft text-success-ink', bubble: 'bg-success-soft' },
  email: { icon: Mail, chip: 'bg-info-soft text-info-ink', bubble: 'bg-info-soft' },
  web_chat: { icon: MessagesSquare, chip: 'bg-warning-soft text-warning-ink', bubble: 'bg-surface-2' },
  ota: { icon: Globe, chip: 'bg-stone-soft text-stone-ink', bubble: 'bg-surface-2' },
  internal_note: { icon: StickyNote, chip: 'bg-warning-soft text-warning-ink', bubble: 'bg-warning-soft' },
}

/** Channels the hotel answers from Housetel on the same thread (web chat and OTA threads only take notes). */
export const REPLY_CHANNELS: ReadonlySet<MessageChannel> = new Set(['email', 'whatsapp'])
