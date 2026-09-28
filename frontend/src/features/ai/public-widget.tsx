import { useQuery } from '@tanstack/react-query'
import { ArrowUp, BedDouble, MessageCircle, X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useLocation } from 'react-router'
import type { PublicWidgetProps } from '@/app/extensions'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { isApiError } from '@/lib/api'
import { LegalLink } from '@/features/saas/components/LegalLink'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import {
  chatBase,
  getChatConfig,
  sendChat,
  sendChatContact,
  type ChatCard,
  type ChatEntry,
  type ChatTarget,
  type Handoff,
} from './api'
import { Markdown } from './components/Markdown'
import { CHAT_OFFSET_VAR } from './lib/chat-offset'

const HEX = /^#[0-9a-f]{6}$/i

/** Readable text on the hotel's brand color (WCAG relative luminance). */
function inkOn(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  })
  const luminance = 0.2126 * r! + 0.7152 * g! + 0.0722 * b!
  return luminance > 0.4 ? '#1F1C19' : '#FFFFFF'
}

function storageKey(target: ChatTarget): string {
  return `housetel.chat.${target.propertySlug ?? `portal.${(target.portalToken ?? '').slice(-24)}`}`
}

function readSession(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function saveSession(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // private mode: the conversation simply won't survive a reload
  }
}

/**
 * Pages where the guest fills a form or pays: the portal and its check-in (`/g/…`) and both checkouts
 * (`/book/…`, `/h/<slug>/book`). On phones the bubble gets smaller there and steps aside while the guest scrolls
 * down, so it never sits on a field or on the pay / confirm button (plan P6).
 */
const FLOW_PAGES = /^\/(g\/|book\/|h\/[^/]+\/book)/
/** Space the bubble takes at the bottom of the screen; pages pad their end with `var(--public-chat-inset)`. */
const CHAT_INSET_VAR = '--public-chat-inset'

/** True after the page scrolled down (hidden), false again on the way up, near the top or at the very end. */
function useScrolledAway(enabled: boolean): boolean {
  const [away, setAway] = useState(false)
  useEffect(() => {
    if (!enabled) return
    let last = window.scrollY
    let frame = 0
    const onScroll = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        const y = window.scrollY
        const atEnd = window.innerHeight + y >= document.documentElement.scrollHeight - 32
        if (y < 80 || atEnd) setAway(false)
        else if (y > last + 8) setAway(true)
        else if (y < last - 8) setAway(false)
        last = y
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.cancelAnimationFrame(frame)
    }
  }, [enabled])
  return enabled && away
}

/**
 * The hotel's chat bubble on public pages (plan C9 · `PublicChatSlot`): only on pages of one hotel (booking
 * engine, hotel page, guest portal) and only when the hotel's chatbot is on (the config answers 404 if not).
 */
export default function PublicWidget({ propertySlug, portalToken }: PublicWidgetProps) {
  if (portalToken) return <ChatWidget target={{ portalToken }} />
  if (propertySlug) return <ChatWidget target={{ propertySlug }} />
  return null
}

function ChatWidget({ target }: { target: ChatTarget }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const key = storageKey(target)
  const [initialSession] = useState(() => readSession(key))
  const config = useQuery({
    queryKey: ['ai', 'public-chat', chatBase(target), lang, initialSession],
    queryFn: () => getChatConfig(target, lang, initialSession),
    retry: false,
    staleTime: Infinity,
  })
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const panelId = useId()
  const { pathname } = useLocation()
  const phone = useMediaQuery('(max-width: 639px)')
  const compact = phone && FLOW_PAGES.test(pathname)
  const enabled = Boolean(config.data?.enabled)
  const hidden = useScrolledAway(compact && enabled && !open) && !focused

  // Tell the page how much room the bubble takes at the bottom (its last content can scroll above it).
  useEffect(() => {
    if (!enabled) return
    const root = document.documentElement
    root.style.setProperty(CHAT_INSET_VAR, compact ? '4.25rem' : '5.5rem')
    return () => {
      root.style.removeProperty(CHAT_INSET_VAR)
    }
  }, [enabled, compact])

  if (!config.data?.enabled) return null
  const hotel = config.data.property.name
  const brand = HEX.test(config.data.property.primary_color) ? config.data.property.primary_color : ''
  const edge = compact ? '0.5rem' : phone ? '0.75rem' : '1.25rem'
  const style = {
    ...(brand ? { '--chat-brand': brand, '--chat-ink': inkOn(brand) } : {}),
    right: edge,
    // above a bar glued to the bottom of the page (the checkout's confirm button) and the phone's home bar
    bottom: `calc(max(${edge}, env(safe-area-inset-bottom)) + var(${CHAT_OFFSET_VAR}, 0px))`,
  } as CSSProperties

  return (
    <div
      style={style}
      className={cn(
        'fixed z-40 flex flex-col items-end gap-3 transition-[translate,opacity] duration-200 ease-out',
        hidden && 'pointer-events-none translate-x-[calc(100%+1rem)] opacity-0',
      )}
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false)
      }}
    >
      {open && (
        <ChatPanel
          id={panelId}
          target={target}
          storage={key}
          hotel={hotel}
          greeting={config.data.greeting}
          suggestions={config.data.suggestions}
          initialMessages={config.data.messages}
          initialSession={config.data.session_id}
          initialHandoff={config.data.handoff}
          lang={lang}
          onClose={() => setOpen(false)}
        />
      )}
      <button
        type="button"
        aria-label={open ? t('widget.close') : t('widget.open', { hotel })}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'grid place-items-center rounded-full shadow-lg transition-transform duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-bg motion-safe:hover:scale-105',
          compact ? 'size-11' : 'size-14',
          brand ? 'bg-[var(--chat-brand)] text-[var(--chat-ink)]' : 'bg-accent text-on-accent',
        )}
      >
        {open ? <X aria-hidden className={compact ? 'size-5' : 'size-6'} /> : <MessageCircle aria-hidden className={compact ? 'size-5' : 'size-6'} />}
      </button>
    </div>
  )
}

interface PanelProps {
  id: string
  target: ChatTarget
  storage: string
  hotel: string
  greeting: string
  suggestions: string[]
  initialMessages: ChatEntry[]
  initialSession: string | null
  initialHandoff: Handoff | null
  lang: 'es' | 'en'
  onClose: () => void
}

function ChatPanel({
  id,
  target,
  storage,
  hotel,
  greeting,
  suggestions,
  initialMessages,
  initialSession,
  initialHandoff,
  lang,
  onClose,
}: PanelProps) {
  const { t } = useTranslation('ai')
  const [messages, setMessages] = useState<ChatEntry[]>(initialMessages)
  const [session, setSession] = useState<string | null>(initialSession)
  const [handoff, setHandoff] = useState<Handoff | null>(initialHandoff)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const inputId = useId()

  useEffect(() => {
    inputRef.current?.focus()
  }, [])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, sending, handoff])

  async function send(question = text) {
    const value = question.trim()
    if (!value || sending) return
    setText('')
    setProblem(null)
    setSending(true)
    setMessages((current) => [...current, { role: 'user', content: value, cards: [], at: null }])
    try {
      const result = await sendChat(target, { message: value, language: lang, session_id: session })
      setSession(result.session_id)
      saveSession(storage, result.session_id)
      setMessages((current) => [...current, result.reply])
      setHandoff(result.handoff)
    } catch (error) {
      setProblem(isApiError(error) && error.status === 429 ? t('widget.rateLimited') : t('widget.error'))
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Escape') onClose()
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send()
    }
  }

  return (
    <section
      id={id}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      style={{ height: `min(34rem, calc(100dvh - 6.5rem - var(${CHAT_OFFSET_VAR}, 0px)))` }}
      className="flex w-[min(23rem,calc(100vw-1rem))] flex-col overflow-hidden rounded-2xl border border-border bg-bg text-[15px] shadow-lg motion-safe:animate-pop-in"
    >
      <header className="flex items-start gap-3 border-b border-border bg-surface px-4 py-3">
        <span aria-hidden className="mt-1 size-2.5 shrink-0 rounded-full border border-border-strong bg-bg" />
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="truncate text-[15px] font-bold text-fg">
            {t('widget.title', { hotel })}
          </h2>
          <p className="text-xs text-muted">{t('widget.subtitle')}</p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label={t('widget.close')} onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        <ol className="flex flex-col gap-3">
          <li>
            <AssistantText content={greeting} />
          </li>
          {messages.map((message, index) => (
            <li key={`${index}-${message.role}`} className="flex flex-col gap-2">
              {message.role === 'user' ? <GuestText content={message.content} /> : <AssistantText content={message.content} />}
              {message.cards.map((card) => (
                <OfferCard key={`${card.room_type_id}-${card.checkin}`} card={card} />
              ))}
            </li>
          ))}
          {sending && (
            <li className="text-sm text-muted" role="status">
              {t('widget.typing')}
            </li>
          )}
        </ol>
        {messages.length === 0 && suggestions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => void send(suggestion)}
                className="rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-fg transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {handoff?.contact_needed && session && (
          <HandoffForm
            target={target}
            session={session}
            onSent={(next) => setHandoff(next)}
          />
        )}
        {handoff?.contact_received && (
          <p className="mt-3 rounded-lg bg-success-soft px-3 py-2 text-[13px] text-success-ink">{t('widget.contactSent')}</p>
        )}
        {problem && (
          <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
            {problem}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void send()
        }}
        className="border-t border-border bg-surface px-3 py-2.5"
      >
        <label htmlFor={inputId} className="sr-only">
          {t('widget.inputLabel')}
        </label>
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            id={inputId}
            name="message"
            rows={1}
            maxLength={1000}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t('widget.placeholder')}
            className="field-sizing-content max-h-32 min-h-10 w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-[15px] text-fg outline-none placeholder:text-subtle focus-visible:border-border-strong focus-visible:ring-2 focus-visible:ring-accent/40"
          />
          <Button type="submit" variant="primary" size="icon" aria-label={t('widget.send')} disabled={!text.trim() || sending}>
            <ArrowUp aria-hidden />
          </Button>
        </div>
        <p className="mt-1 text-center text-[10.5px] text-subtle">{t('widget.poweredBy')}</p>
      </form>
    </section>
  )
}

function AssistantText({ content }: { content: string }) {
  return (
    <div className="max-w-[90%] rounded-2xl rounded-bl-md bg-surface px-3.5 py-2 shadow-xs">
      <Markdown className="text-[14px]">{content}</Markdown>
    </div>
  )
}

function GuestText({ content }: { content: string }) {
  return (
    <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-surface-3 px-3.5 py-2 text-[14px] whitespace-pre-wrap text-fg">
      {content}
    </p>
  )
}

/** One room type offered for the dates the guest asked, with the link to book it in the booking engine. */
function OfferCard({ card }: { card: ChatCard }) {
  const { t } = useTranslation('ai')
  const titleId = useId()
  return (
    <article aria-labelledby={titleId} className="max-w-[90%] rounded-xl border border-border bg-surface px-3.5 py-3 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <h3 id={titleId} className="flex items-center gap-1.5 text-[14px] font-bold text-fg">
          <BedDouble aria-hidden className="size-4 text-muted" />
          {card.room_type}
        </h3>
        {card.available <= 3 && (
          <span className="shrink-0 rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-semibold text-warning-ink">
            {t('widget.left', { count: card.available })}
          </span>
        )}
      </div>
      <p className="num mt-1 text-[15px] font-bold text-fg">{t('widget.perNight', { price: formatMoney(card.per_night, card.currency) })}</p>
      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="num text-[12.5px] text-muted">
          {t('widget.total', { total: formatMoney(card.total, card.currency), count: card.nights })}
        </p>
        <Button asChild size="sm" variant="primary">
          <a href={card.url}>{t('widget.book')}</a>
        </Button>
      </div>
    </article>
  )
}

function HandoffForm({ target, session, onSent }: { target: ChatTarget; session: string; onSent: (handoff: Handoff) => void }) {
  const { t } = useTranslation('ai')
  const [values, setValues] = useState({ name: '', email: '', phone: '', message: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const formId = useId()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!values.name.trim() || (!values.email.trim() && !values.phone.trim())) {
      setProblem(t('widget.contactNeeded'))
      return
    }
    setSending(true)
    setProblem(null)
    try {
      const result = await sendChatContact(target, { session_id: session, ...values })
      onSent(result.handoff)
    } catch (error) {
      setProblem(isApiError(error) && error.fields ? Object.values(error.fields).flat()[0] ?? t('widget.error') : t('widget.error'))
    } finally {
      setSending(false)
    }
  }

  const field = (name: keyof typeof values, type = 'text', autoComplete?: string) => (
    <div className="flex flex-col gap-1">
      <label htmlFor={`${formId}-${name}`} className="text-[12.5px] font-semibold text-muted">
        {t(`widget.${name}`)}
      </label>
      <Input
        id={`${formId}-${name}`}
        name={name}
        type={type}
        autoComplete={autoComplete}
        value={values[name]}
        onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
        className="h-9 text-[14px]"
      />
    </div>
  )

  return (
    <form
      aria-label={t('widget.handoffTitle')}
      onSubmit={submit}
      noValidate
      className="mt-3 flex flex-col gap-2.5 rounded-xl border border-border bg-surface px-3.5 py-3 shadow-xs"
    >
      <div>
        <p className="text-[14px] font-bold text-fg">{t('widget.handoffTitle')}</p>
        <p className="text-[12.5px] text-muted">{t('widget.handoffText')}</p>
      </div>
      {field('name', 'text', 'name')}
      {field('email', 'email', 'email')}
      {field('phone', 'tel', 'tel')}
      {field('message')}
      {problem && (
        <p role="alert" className="text-[12.5px] text-danger-ink">
          {problem}
        </p>
      )}
      <Button type="submit" size="sm" loading={sending}>
        {t('widget.sendContact')}
      </Button>
      <p className="text-[11.5px] leading-4 text-muted">
        <Trans t={t} i18nKey="widget.privacy" components={{ privacy: <LegalLink to="/legal/privacidad" /> }} />
      </p>
    </form>
  )
}
