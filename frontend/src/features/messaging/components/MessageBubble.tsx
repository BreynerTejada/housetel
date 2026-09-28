import { FileText, Sparkles, StickyNote } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Message } from '../api'
import { CHANNEL_META } from '../lib/channels'
import { DeliveryStatus } from './ChannelMark'
import { Linkified } from './Linkified'
import { WhatsAppText } from './WhatsAppText'

function clock(value: string): string {
  return formatDate(value, 'HH:mm')
}

/**
 * One message of a thread. The guest's messages sit on the left on white paper; the hotel's on the
 * right, tinted with the channel color; internal notes are the front desk's message slips (sand, with a
 * perforated top edge) that the guest never sees.
 */
export function MessageBubble({ message, templateLabels = {} }: { message: Message; templateLabels?: Record<string, string> }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const time = (
    <time dateTime={message.created_at} className="num" title={formatDate(message.created_at, 'PPPp', lang)}>
      {clock(message.created_at)}
    </time>
  )

  if (message.channel === 'internal_note') {
    return (
      <li className="flex justify-end" data-kind="note">
        <article className="relative w-fit max-w-[min(30rem,88%)] rounded-lg rounded-t-sm bg-warning-soft px-3.5 pt-3 pb-2 shadow-xs">
          <span
            aria-hidden
            className="absolute inset-x-2 -top-[3px] h-[6px] bg-[radial-gradient(circle,var(--bg)_2px,transparent_2.6px)] bg-[length:10px_6px] bg-repeat-x"
          />
          <p className="eyebrow flex items-center gap-1.5 !text-warning-ink">
            <StickyNote aria-hidden className="size-3" />
            {t('inbox.noteLabel')}
            <span className="font-medium tracking-normal normal-case">· {t('inbox.noteHint')}</span>
          </p>
          <p className="mt-1 text-[14px] leading-relaxed break-words whitespace-pre-wrap text-fg">{message.body}</p>
          <footer className="mt-1 flex justify-end gap-2 text-[11px] text-warning-ink">
            <span>{message.sender_label}</span>
            {time}
          </footer>
        </article>
      </li>
    )
  }

  const outbound = message.direction === 'out'
  const meta = CHANNEL_META[message.channel] ?? CHANNEL_META.ota
  const templateName = message.template_code ? (templateLabels[message.template_code] ?? message.template_code) : ''
  return (
    <li className={cn('flex', outbound ? 'justify-end' : 'justify-start')} data-direction={message.direction}>
      <article
        className={cn(
          'w-fit max-w-[min(34rem,88%)] rounded-2xl px-3.5 py-2.5 shadow-xs',
          outbound ? cn(meta.bubble, 'rounded-br-md') : 'rounded-bl-md border border-border bg-surface',
          message.status === 'failed' && 'ring-1 ring-danger/40',
        )}
      >
        {message.subject && <p className="mb-1 text-[13px] font-bold break-words text-fg">{message.subject}</p>}
        <p className="text-[14px] leading-relaxed break-words whitespace-pre-wrap text-fg">
          {message.channel === 'whatsapp' ? <WhatsAppText text={message.body} /> : <Linkified text={message.body} />}
        </p>
        <footer className="mt-1.5 flex flex-wrap items-center justify-end gap-x-2 gap-y-0.5 text-[11px] text-muted">
          {templateName && (
            <span className="inline-flex items-center gap-1">
              <FileText aria-hidden className="size-3" />
              {t('inbox.template', { name: templateName })}
            </span>
          )}
          {message.ai_generated && (
            <span className="inline-flex items-center gap-1">
              <Sparkles aria-hidden className="size-3" />
              {t('inbox.aiDraft')}
            </span>
          )}
          {message.sender_label && <span className="max-w-[16rem] truncate">{message.sender_label}</span>}
          {time}
          {outbound && <DeliveryStatus status={message.status} />}
        </footer>
        {message.status === 'failed' && message.error && (
          <p className="mt-1.5 border-t border-danger/20 pt-1.5 text-[12px] leading-snug text-danger-ink">{message.error}</p>
        )}
      </article>
    </li>
  )
}
