import { BatteryFull, CheckCheck, ChevronLeft, SendHorizontal, Signal, Wifi } from 'lucide-react'
import { useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Message } from '../api'
import { WhatsAppText } from './WhatsAppText'

/**
 * A phone showing the guest's WhatsApp chat with the hotel. Seen from the guest's side: what the guest
 * writes is on the right (green), the hotel's replies on the left.
 */
export function PhoneMockup({
  label,
  hotelName,
  messages,
  notice,
  disabled,
  sending,
  onSend,
  footer,
}: {
  label: string
  hotelName: string
  messages: Message[]
  notice?: string
  disabled?: boolean
  sending?: boolean
  onSend: (body: string) => Promise<unknown> | void
  footer?: ReactNode
}) {
  const { t } = useTranslation('messaging')
  const [draft, setDraft] = useState('')
  const chat = useRef<HTMLDivElement>(null)
  const lastId = messages.at(-1)?.id

  useLayoutEffect(() => {
    if (chat.current) chat.current.scrollTop = chat.current.scrollHeight
  }, [lastId])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const body = draft.trim()
    if (!body || disabled) return
    try {
      await onSend(body)
      setDraft('')
    } catch {
      // Not sent (the page shows why): the draft stays so it can be sent again.
    }
  }

  return (
    <section aria-label={label} className="mx-auto w-full max-w-[360px]">
      <div className="rounded-[2.6rem] bg-[#1f1c19] p-2.5 shadow-lg ring-1 ring-black/10">
        <div className="relative flex h-[640px] max-h-[calc(100dvh-10rem)] min-h-[480px] flex-col overflow-hidden rounded-[2.1rem] bg-surface-2">
          {/* status bar */}
          <div className="relative flex h-9 shrink-0 items-center justify-between bg-surface px-6 text-[12px] font-semibold text-fg">
            <span className="num">{formatDate(new Date(), 'HH:mm')}</span>
            <span aria-hidden className="absolute top-2 left-1/2 h-5 w-24 -translate-x-1/2 rounded-full bg-[#1f1c19]" />
            <span className="flex items-center gap-1" aria-hidden>
              <Signal className="size-3.5" />
              <Wifi className="size-3.5" />
              <BatteryFull className="size-4" />
            </span>
          </div>
          {/* chat header */}
          <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface px-3 pb-2.5">
            <ChevronLeft aria-hidden className="size-5 text-success-ink" />
            <span aria-hidden className="grid size-9 place-items-center rounded-full bg-accent text-[15px] font-bold text-on-accent">
              {hotelName.trim().charAt(0).toUpperCase()}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[14px] leading-5 font-bold">{hotelName}</span>
              <span className="block text-[11px] text-success-ink">{t('simulator.online')}</span>
            </span>
          </div>
          {/* messages */}
          <div
            ref={chat}
            className="hatch min-h-0 flex-1 overflow-y-auto px-3 py-3"
            aria-live="polite"
            aria-relevant="additions"
          >
            {notice && (
              <p className="mx-auto mb-3 w-fit max-w-[90%] rounded-lg bg-warning-soft px-3 py-1.5 text-center text-[11.5px] text-warning-ink shadow-xs">
                {notice}
              </p>
            )}
            {messages.length === 0 ? (
              <p className="mx-auto mt-8 w-fit rounded-lg bg-surface px-3 py-1.5 text-[12px] text-muted shadow-xs">
                {t('simulator.emptyChat')}
              </p>
            ) : (
              <ol className="grid gap-1.5">
                {messages.map((message) => {
                  const mine = message.direction === 'in'
                  return (
                    <li key={message.id} className={cn('flex', mine ? 'justify-end' : 'justify-start')}>
                      <p
                        className={cn(
                          'max-w-[82%] rounded-xl px-2.5 pt-1.5 pb-1 text-[13.5px] leading-snug break-words whitespace-pre-wrap shadow-xs',
                          mine ? 'rounded-tr-sm bg-success-soft text-fg' : 'rounded-tl-sm bg-surface text-fg',
                        )}
                      >
                        {message.subject && <strong className="block">{message.subject}</strong>}
                        <WhatsAppText text={message.body} />
                        <span className="float-right mt-1 ml-2 flex items-center gap-0.5 text-[10px] text-muted">
                          <span className="num">{formatDate(message.created_at, 'HH:mm')}</span>
                          {mine && <CheckCheck aria-hidden className="size-3 text-info-ink" />}
                        </span>
                      </p>
                    </li>
                  )
                })}
              </ol>
            )}
          </div>
          {/* input */}
          <form onSubmit={submit} className="flex shrink-0 items-end gap-2 bg-surface-2 px-2.5 pt-1.5 pb-4">
            <label className="min-w-0 flex-1">
              <span className="sr-only">{t('simulator.typeMessage')}</span>
              <textarea
                name="body"
                rows={1}
                value={draft}
                disabled={disabled}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
                placeholder={t('simulator.typeMessage')}
                className="block max-h-28 min-h-10 w-full resize-none rounded-3xl border border-border bg-surface px-4 py-2.5 text-[14px] leading-5 text-fg shadow-xs outline-none placeholder:text-subtle focus-visible:border-success focus-visible:ring-2 focus-visible:ring-success/25 disabled:opacity-60"
              />
            </label>
            <button
              type="submit"
              disabled={disabled || sending || !draft.trim()}
              aria-label={t('simulator.send')}
              className="grid size-10 shrink-0 place-items-center rounded-full bg-success text-on-accent shadow-sm transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-success/40 focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-45"
            >
              <SendHorizontal aria-hidden className="size-4.5" />
            </button>
          </form>
        </div>
      </div>
      {footer && <div className="mt-4 flex justify-center">{footer}</div>}
    </section>
  )
}
