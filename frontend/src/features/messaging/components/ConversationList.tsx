import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { initials } from '@/components/ui/avatar'
import { GuestAvatar } from '@/features/guests/components/GuestAvatar'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Conversation } from '../api'
import { listTime } from '../lib/thread'
import { ChannelMark } from './ChannelMark'

/**
 * One thread of the inbox, read like the key rack behind reception: the guest's tag (warm when VIP) with the
 * channel pinned to it, and the room key when the booking has one.
 */
export function ConversationRow({ conversation, href, selected }: { conversation: Conversation; href: string; selected: boolean }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const unread = conversation.unread_count
  const reservation = conversation.reservation
  const preview = conversation.last_message_preview || t('inbox.noPreview')
  return (
    <Link
      to={href}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-b border-border px-4 py-3 transition-colors outline-none',
        'hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-inset',
        selected && 'bg-accent-soft/55 hover:bg-accent-soft/70',
      )}
    >
      <span className="relative self-start">
        <GuestAvatar name={conversation.display_name} vip={conversation.guest?.is_vip} />
        <ChannelMark channel={conversation.channel} className="absolute -right-1.5 -bottom-1.5 ring-2 ring-bg" />
      </span>
      <span className="grid min-w-0 gap-0.5">
        <span className="flex items-baseline gap-2">
          <span className={cn('truncate text-[14px]', unread ? 'font-bold text-fg' : 'font-semibold text-fg')}>
            {conversation.display_name}
          </span>
          <time
            dateTime={conversation.last_message_at ?? undefined}
            className={cn('num ml-auto shrink-0 text-[11px]', unread ? 'font-bold text-accent-ink' : 'text-muted')}
          >
            {listTime(conversation.last_message_at, lang)}
          </time>
        </span>
        <span className="flex items-center gap-2">
          <span className={cn('truncate text-[13px]', unread ? 'text-fg' : 'text-muted')}>
            {conversation.last_message_direction === 'out' && <span className="text-muted">{t('inbox.you')}: </span>}
            {preview}
          </span>
          {unread > 0 && (
            <span
              className="num ml-auto grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-accent px-1.5 text-[11px] font-bold text-on-accent"
              aria-label={t('inbox.unreadBadge', { count: unread })}
            >
              {unread}
            </span>
          )}
        </span>
        {(reservation || conversation.assigned_to) && (
          <span className="mt-1 flex items-center gap-2 text-[11px] text-muted">
            {reservation?.room && <RoomKeyTag number={reservation.room} status="occupied" size="sm" className="h-6 min-w-9" />}
            {reservation && <span className="num truncate">{reservation.code}</span>}
            {conversation.assigned_to && (
              <span
                className="ml-auto grid size-5 shrink-0 place-items-center rounded-full bg-surface-3 text-[9px] font-bold text-muted"
                title={t('inbox.actions.assignedTo', { name: conversation.assigned_to.full_name })}
              >
                {initials(conversation.assigned_to.full_name, conversation.assigned_to.email)}
              </span>
            )}
          </span>
        )}
      </span>
    </Link>
  )
}

export function ConversationListEmpty({ filtered, action }: { filtered: boolean; action?: ReactNode }) {
  const { t } = useTranslation('messaging')
  return (
    <EmptyState
      icon={Inbox}
      title={t('inbox.emptyTitle')}
      description={filtered ? t('inbox.emptyFiltered') : t('inbox.emptyOpen')}
      action={action}
    />
  )
}
