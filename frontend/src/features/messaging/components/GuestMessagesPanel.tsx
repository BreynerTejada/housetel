import { ArrowUpRight, MessagesSquare, PenLine } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatRelative, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useConversations, useMessages, useTemplates, type Conversation } from '../api'
import { templateOptions } from '../lib/templates'
import { ChannelMark } from './ChannelMark'
import { MessageBubble } from './MessageBubble'
import { SendDialog } from './SendDialog'

const LAST_MESSAGES = 4

/**
 * Tab "Messages" of a reservation or a guest profile: the guest's threads with their latest messages, a way
 * to write to the guest and a link to answer from the inbox.
 */
export default function GuestMessagesPanel({ reservationId, guestId }: { reservationId?: string; guestId?: string }) {
  const { t } = useTranslation('messaging')
  const canSend = useCan('messaging.send')
  const [writing, setWriting] = useState(false)
  const conversations = useConversations(reservationId ? { reservation: reservationId, page_size: 20 } : { guest: guestId, page_size: 20 })
  const rows = conversations.data?.results ?? []

  const write = canSend && (
    <Button variant="primary" onClick={() => setWriting(true)}>
      <PenLine aria-hidden />
      {t('tab.write')}
    </Button>
  )

  return (
    <section aria-labelledby="guest-messages-title" className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="guest-messages-title" className="text-base font-bold">
            {t('tab.title')}
          </h2>
          <p className="text-[13px] text-muted">{t('tab.description')}</p>
        </div>
        {rows.length > 0 && write}
      </div>
      {conversations.isPending ? (
        <LoadingState variant="rows" rows={3} />
      ) : conversations.isError ? (
        <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} />
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-strong">
          <EmptyState icon={MessagesSquare} title={t('tab.empty')} description={t('tab.emptyHint')} action={write || undefined} />
        </div>
      ) : (
        <ul className="grid gap-4">
          {rows.map((conversation) => (
            <li key={conversation.id}>
              <ThreadCard conversation={conversation} />
            </li>
          ))}
        </ul>
      )}
      <SendDialog
        open={writing}
        onOpenChange={setWriting}
        reservationId={reservationId}
        guestId={reservationId ? undefined : guestId}
      />
    </section>
  )
}

function ThreadCard({ conversation }: { conversation: Conversation }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const canOpenInbox = useCan('messaging.view')
  const messages = useMessages(conversation.id)
  const templates = useTemplates()
  const labels = Object.fromEntries(templateOptions(templates.data, lang).map((option) => [option.code, option.label]))
  const all = messages.data?.results ?? []
  const latest = all.slice(-LAST_MESSAGES)
  const earlier = all.length > latest.length || Boolean(messages.data?.has_more)

  return (
    <article className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border px-4 py-3">
        <ChannelMark channel={conversation.channel} withLabel />
        <span className="num min-w-0 truncate text-[13px] text-muted">{conversation.address}</span>
        {conversation.status === 'closed' && <Badge tone="stone">{t('inbox.views.closed')}</Badge>}
        {conversation.unread_count > 0 && <Badge tone="accent">{t('inbox.unreadBadge', { count: conversation.unread_count })}</Badge>}
        <span className="ml-auto text-[12px] text-muted">
          {conversation.last_message_at && t('tab.lastActivity', { when: formatRelative(conversation.last_message_at, lang) })}
        </span>
      </header>
      <div className="bg-bg px-3 py-3 sm:px-4">
        {messages.isPending ? (
          <LoadingState variant="rows" rows={2} />
        ) : messages.isError ? (
          <ErrorState error={messages.error} onRetry={() => messages.refetch()} />
        ) : (
          <>
            {earlier && <p className="mb-2 text-center text-[12px] text-muted">{t('tab.earlier')}</p>}
            <ol className="grid gap-2" aria-label={t('inbox.threadLabel', { name: conversation.display_name })}>
              {latest.map((message) => (
                <MessageBubble key={message.id} message={message} templateLabels={labels} />
              ))}
            </ol>
          </>
        )}
      </div>
      {canOpenInbox && (
        <footer className="flex justify-end border-t border-border px-4 py-2.5">
          <Link to={`/app/inbox?c=${conversation.id}`} className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
            {t('tab.open')}
            <ArrowUpRight aria-hidden className="size-3.5" />
          </Link>
        </footer>
      )}
    </article>
  )
}
