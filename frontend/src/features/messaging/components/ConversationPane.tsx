import { Archive, ArchiveRestore, ArrowLeft, Clock, Info, PanelRight, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { GuestAvatar } from '@/features/guests/components/GuestAvatar'
import { useActiveProperty, useMe } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  assignConversation,
  closeConversation,
  markRead,
  reopenConversation,
  useConversation,
  useMessagingMutation,
  useTeamMembers,
  type ConversationDetail,
} from '../api'
import { windowHoursLeft } from '../lib/thread'
import { ChannelMark } from './ChannelMark'
import { Composer } from './Composer'
import { ContextPanel } from './ContextPanel'
import { useThreadMessages } from '../lib/useThreadMessages'
import { Thread } from './Thread'

/**
 * The open conversation: header with the guest and the thread's actions, the messages, the reply box and
 * (on wide screens) the booking beside it. Mount it with `key={conversationId}`.
 */
export function ConversationPane({ conversationId, backHref }: { conversationId: string; backHref: string }) {
  const { t } = useTranslation('messaging')
  const detail = useConversation(conversationId)
  const thread = useThreadMessages(conversationId)
  const [contextOpen, setContextOpen] = useState(false)
  const read = useMessagingMutation(() => markRead(conversationId))
  const readOnce = useRef(false)
  const unread = detail.data?.unread_count ?? 0

  // Opening a thread with messages waiting marks it read (once per opening).
  useEffect(() => {
    if (unread > 0 && !readOnce.current) {
      readOnce.current = true
      read.mutate(undefined)
    }
  }, [unread, read])

  if (detail.isPending) return <LoadingState variant="rows" rows={6} className="flex-1 p-6" />
  if (detail.isError)
    return (
      <div className="flex-1">
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    )

  const conversation = detail.data
  const lastInbound = [...thread.messages].reverse().find((message) => message.direction === 'in')

  return (
    <div className="flex min-w-0 flex-1">
      <section aria-label={conversation.display_name} className="flex min-w-0 flex-1 flex-col">
        <PaneHeader conversation={conversation} backHref={backHref} onOpenContext={() => setContextOpen(true)} />
        <ThreadBanner conversation={conversation} />
        <Thread thread={thread} label={t('inbox.threadLabel', { name: conversation.display_name })} />
        <Composer conversation={conversation} lastInbound={lastInbound} />
      </section>
      <aside
        aria-label={t('context.title')}
        className="hidden w-[320px] shrink-0 overflow-y-auto border-l border-border bg-surface-2/40 xl:block"
      >
        <ContextPanel conversation={conversation} />
      </aside>
      <Sheet open={contextOpen} onOpenChange={setContextOpen}>
        <SheetContent side="right" className="xl:hidden">
          <SheetHeader>
            <SheetTitle>{t('context.title')}</SheetTitle>
            <SheetDescription>{conversation.display_name}</SheetDescription>
          </SheetHeader>
          <SheetBody className="p-0">
            <ContextPanel conversation={conversation} />
          </SheetBody>
        </SheetContent>
      </Sheet>
    </div>
  )
}

function PaneHeader({
  conversation,
  backHref,
  onOpenContext,
}: {
  conversation: ConversationDetail
  backHref: string
  onOpenContext: () => void
}) {
  const { t } = useTranslation('messaging')
  const canSend = useCan('messaging.send')
  const closed = conversation.status === 'closed'
  const toggle = useMessagingMutation(
    () => (closed ? reopenConversation(conversation.id) : closeConversation(conversation.id)),
    { onSuccess: () => toast.success(closed ? t('inbox.actions.reopened') : t('inbox.actions.closed')) },
  )

  return (
    <header className="flex items-center gap-3 border-b border-border bg-surface px-3 py-2.5 sm:px-4">
      <Button asChild variant="ghost" size="icon-sm" className="md:hidden">
        <Link to={backHref} aria-label={t('inbox.back')}>
          <ArrowLeft aria-hidden />
        </Link>
      </Button>
      <GuestAvatar name={conversation.display_name} vip={conversation.guest?.is_vip} size="sm" />
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] leading-5 font-bold">{conversation.display_name}</h2>
        <p className="flex min-w-0 items-center gap-1.5 text-[12px] text-muted">
          <ChannelMark channel={conversation.channel} withLabel />
          <span className="num truncate">{conversation.address}</span>
        </p>
      </div>
      {canSend && <AssignMenu conversation={conversation} />}
      {canSend && (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => toggle.mutate(undefined, { onError: (error) => toast.error(errorMessage(error, t)) })}
          loading={toggle.isPending}
        >
          {!toggle.isPending && (closed ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />)}
          <span className="hidden sm:inline">{closed ? t('inbox.actions.reopen') : t('inbox.actions.close')}</span>
        </Button>
      )}
      <Button variant="ghost" size="icon-sm" className="xl:hidden" onClick={onOpenContext} aria-label={t('inbox.contextButton')}>
        <PanelRight aria-hidden />
      </Button>
    </header>
  )
}

function AssignMenu({ conversation }: { conversation: ConversationDetail }) {
  const { t } = useTranslation('messaging')
  const { data: me } = useMe()
  const { property } = useActiveProperty()
  const canPickAnyone = useCan('accounts.users_manage')
  const members = useTeamMembers(canPickAnyone)
  const assign = useMessagingMutation((userId: string | null) => assignConversation(conversation.id, userId), {
    onSuccess: (_, userId) => toast.success(userId ? t('inbox.actions.assignedToast') : t('inbox.actions.unassignedToast')),
  })
  const assigned = conversation.assigned_to
  const colleagues = canPickAnyone
    ? (members.data?.results ?? []).filter(
        (member) =>
          member.is_active &&
          member.user.id !== me?.id &&
          member.user.id !== assigned?.id &&
          (member.all_properties || member.properties.some((item) => item.id === property?.id)),
      )
    : []

  function run(userId: string | null) {
    assign.mutate(userId, { onError: (error) => toast.error(errorMessage(error, t)) })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className={cn('max-w-44', assigned && 'text-fg')} loading={assign.isPending}>
          {!assign.isPending && <UserRound aria-hidden />}
          <span className="hidden truncate lg:inline">
            {assigned ? t('inbox.actions.assignedTo', { name: assigned.full_name || assigned.email }) : t('inbox.actions.assign')}
          </span>
          <span className="sr-only lg:hidden">{t('inbox.actions.assign')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel>
          {assigned ? t('inbox.actions.assignedTo', { name: assigned.full_name || assigned.email }) : t('inbox.actions.unassigned')}
        </DropdownMenuLabel>
        {me && assigned?.id !== me.id && <DropdownMenuItem onSelect={() => run(me.id)}>{t('inbox.actions.assignMe')}</DropdownMenuItem>}
        {colleagues.map((member) => (
          <DropdownMenuItem key={member.id} onSelect={() => run(member.user.id)}>
            {t('inbox.actions.assignTo', { name: member.user.full_name || member.user.email })}
          </DropdownMenuItem>
        ))}
        {assigned && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => run(null)}>{t('inbox.actions.unassign')}</DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ThreadBanner({ conversation }: { conversation: ConversationDetail }) {
  const { t } = useTranslation('messaging')
  if (conversation.status === 'closed') {
    return (
      <p className="flex items-center gap-2 border-b border-border bg-stone-soft px-4 py-2 text-[12.5px] text-stone-ink">
        <Archive aria-hidden className="size-3.5 shrink-0" />
        {t('inbox.closedBanner')}
      </p>
    )
  }
  if (conversation.channel !== 'whatsapp') return null
  const hours = windowHoursLeft(conversation.last_inbound_at)
  if (conversation.whatsapp_window_open) {
    return (
      <p className="flex items-center gap-2 border-b border-border bg-success-soft px-4 py-1.5 text-[12.5px] text-success-ink">
        <Clock aria-hidden className="size-3.5 shrink-0" />
        {hours === null || hours === 0 ? t('inbox.window.closing') : t('inbox.window.open', { count: hours })}
      </p>
    )
  }
  return (
    <p className="flex items-start gap-2 border-b border-border bg-warning-soft px-4 py-1.5 text-[12.5px] text-warning-ink">
      <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      {t('inbox.window.closed')}
    </p>
  )
}
