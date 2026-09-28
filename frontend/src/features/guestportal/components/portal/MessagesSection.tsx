import { Mail, MessageCircle, MessagesSquare } from 'lucide-react'
import { Fragment, useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { PortalMessage, PortalProperty } from '../../api'
import { formatHotelDateTime } from '../../lib/text'
import { HotelMark } from './PortalFrame'

const COLLAPSED = 3
const CHANNEL_ICON: Record<string, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
  email: Mail,
  whatsapp: MessageCircle,
}
const URL_PATTERN = /(https?:\/\/[^\s<>"')]+)/g
const BOLD_PATTERN = /\*([^*\n]+)\*/g // WhatsApp's *bold*

/** WhatsApp-style `*bold*` inside a plain-text run. */
function Emphasis({ text }: { text: string }) {
  const parts = text.split(BOLD_PATTERN)
  return <>{parts.map((part, index) => (index % 2 === 1 ? <strong key={index}>{part}</strong> : <Fragment key={index}>{part}</Fragment>))}</>
}

/** Plain text with its web addresses turned into links (message bodies are plain text, never HTML). */
function Linkified({ text }: { text: string }) {
  const parts = text.split(URL_PATTERN)
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <a key={index} href={part} className="font-semibold break-all text-accent-ink underline underline-offset-2">
            {part}
          </a>
        ) : (
          <Emphasis key={index} text={part} />
        ),
      )}
    </>
  )
}

/**
 * What the hotel wrote about this booking (confirmation, pre-arrival, replies) and what the guest answered,
 * by email or WhatsApp — the thread lives in the hotel's inbox (C6); here it is read-only. To write, the
 * guest uses the chat bubble of the page.
 */
export function MessagesSection({ messages, property }: { messages: PortalMessage[]; property: PortalProperty }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [all, setAll] = useState(false)
  if (!messages.length) return null
  const shown = all ? messages : messages.slice(-COLLAPSED)

  return (
    <section aria-labelledby="messages-title" className="grid gap-3">
      <div>
        <h2 id="messages-title" className="text-lg font-bold">
          {t('messages.title')}
        </h2>
        <p className="text-sm text-muted">{t('messages.hint')}</p>
      </div>
      {messages.length > shown.length && (
        <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setAll(true)}>
          {t('messages.showAll', { count: messages.length })}
        </Button>
      )}
      <ol className="grid gap-3">
        {shown.map((message) => {
          const mine = message.direction === 'in'
          const Icon = CHANNEL_ICON[message.channel] ?? MessagesSquare
          const when = formatHotelDateTime(message.created_at, property.timezone, lang)
          return (
            <li key={message.id} className={cn('flex items-end gap-2', mine && 'flex-row-reverse')}>
              {!mine && <HotelMark property={property} size="sm" />}
              <article
                className={cn(
                  'min-w-0 max-w-[88%] rounded-2xl px-4 py-3 text-sm shadow-xs',
                  mine ? 'rounded-br-md bg-accent-soft text-fg' : 'rounded-bl-md border border-border bg-surface',
                )}
              >
                <header className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-muted">
                  <span className="font-semibold text-fg">{mine ? t('messages.you') : property.name}</span>
                  <span className="inline-flex items-center gap-1">
                    <Icon aria-hidden className="size-3.5" />
                    {t(`messages.channels.${message.channel}`, { defaultValue: t('messages.channels.web_chat') })}
                  </span>
                  <time dateTime={message.created_at}>{when}</time>
                </header>
                {message.subject && <p className="mb-1 font-bold">{message.subject}</p>}
                <MessageBody body={message.body} />
              </article>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function MessageBody({ body }: { body: string }) {
  const { t } = useTranslation('guestportal')
  const long = body.length > 280 || body.split('\n').length > 6
  const [open, setOpen] = useState(!long)
  return (
    <div className="grid gap-1">
      <p className={cn('break-words whitespace-pre-line', !open && 'line-clamp-5')}>
        <Linkified text={body} />
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="justify-self-start text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          aria-expanded={open}
        >
          {open ? t('messages.less') : t('messages.more')}
        </button>
      )}
    </div>
  )
}
