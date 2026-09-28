import { MessagesSquare, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useConversations, useUnreadCount, type Channel, type ConversationFilters } from '../api'
import { ConversationListEmpty, ConversationRow } from '../components/ConversationList'
import { ConversationPane } from '../components/ConversationPane'

const VIEWS = ['open', 'unread', 'mine', 'unassigned', 'closed'] as const
type View = (typeof VIEWS)[number]
const CHANNELS: Channel[] = ['whatsapp', 'email', 'web_chat', 'ota']
const PAGE = 30

function asView(value: string | null): View {
  return VIEWS.includes(value as View) ? (value as View) : 'open'
}

function filtersFor(view: View, channel: Channel | null, q: string): ConversationFilters {
  const filters: ConversationFilters = view === 'closed' ? { status: 'closed' } : { status: 'open' }
  if (view === 'unread') filters.unread = true
  if (view === 'mine') filters.assigned = 'me'
  if (view === 'unassigned') filters.assigned = 'none'
  if (channel) filters.channel = channel
  if (q) filters.q = q
  return filters
}

/**
 * `/app/inbox`: the unified inbox. Conversations on the left (filters in the URL), the open thread with
 * its reply box in the middle and the guest's booking on the right. On phones the list and the thread
 * are two screens.
 */
export default function InboxPage() {
  const { t } = useTranslation('messaging')
  const [params, setParams] = useSearchParams()
  const selected = params.get('c')
  const view = asView(params.get('view'))
  const channelParam = params.get('channel')
  const channel = CHANNELS.includes(channelParam as Channel) ? (channelParam as Channel) : null
  const q = params.get('q') ?? ''
  const [search, setSearch] = useState(q)
  const [limit, setLimit] = useState(PAGE)
  const canSimulate = useCan('messaging.send')
  const filters = useMemo(() => ({ ...filtersFor(view, channel, q), page_size: limit }), [view, channel, q, limit])
  const conversations = useConversations(filters)
  const unread = useUnreadCount()

  function update(changes: Record<string, string | null>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value)
          else next.delete(key)
        }
        return next
      },
      { replace: true },
    )
  }

  // The search box writes to the URL after a short pause.
  useEffect(() => {
    const trimmed = search.trim()
    if (trimmed === q) return
    const id = window.setTimeout(() => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          if (trimmed) next.set('q', trimmed)
          else next.delete('q')
          return next
        },
        { replace: true },
      )
    }, 300)
    return () => window.clearTimeout(id)
  }, [search, q, setParams])

  function hrefWith(changes: Record<string, string | null>): string {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    const query = next.toString()
    return query ? `?${query}` : '?'
  }

  const rows = conversations.data?.results ?? []
  const total = conversations.data?.count ?? 0
  const waiting = unread.data?.conversations ?? 0
  const filtered = view !== 'open' || Boolean(channel) || Boolean(q)

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-3.5rem)] min-h-[30rem] overflow-hidden bg-bg sm:-mx-6 lg:-mx-8 lg:-my-8">
      <nav
        aria-label={t('inbox.listLabel')}
        className={cn(
          'flex w-full shrink-0 flex-col border-r border-border bg-surface md:w-[340px] lg:w-[360px]',
          selected && 'hidden md:flex',
        )}
      >
        <div className="grid gap-3 border-b border-border px-4 pt-4 pb-3">
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="text-[20px] leading-7 tracking-[-0.025em]">{t('inbox.title')}</h1>
            <p className={cn('text-[12px]', waiting ? 'font-semibold text-accent-ink' : 'text-muted')}>
              {waiting ? t('inbox.waiting', { count: waiting }) : t('inbox.allAnswered')}
            </p>
          </div>
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input
              type="search"
              name="q"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label={t('inbox.search')}
              placeholder={t('inbox.search')}
              className="pl-9"
            />
          </div>
          <div className="flex items-center gap-2">
            <ToggleGroup
              type="single"
              value={view}
              onValueChange={(value) => {
                if (!value) return
                setLimit(PAGE)
                update({ view: value === 'open' ? null : value })
              }}
              aria-label={t('inbox.viewsLabel')}
              className="min-w-0 flex-1 overflow-x-auto [scrollbar-width:none]"
            >
              {VIEWS.map((item) => (
                <ToggleGroupItem key={item} value={item} className="shrink-0 px-2">
                  {t(`inbox.views.${item}`)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
          <Select
            value={channel ?? 'all'}
            onValueChange={(value) => update({ channel: value === 'all' ? null : value })}
            name="channel"
          >
            <SelectTrigger aria-label={t('inbox.channel')} className="h-8 text-[13px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('inbox.allChannels')}</SelectItem>
              {CHANNELS.map((item) => (
                <SelectItem key={item} value={item}>
                  {t(`channels.${item}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversations.isPending ? (
            <LoadingState variant="rows" rows={6} className="p-4" />
          ) : conversations.isError ? (
            <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} />
          ) : rows.length === 0 ? (
            <ConversationListEmpty
              filtered={filtered}
              action={
                !filtered && canSimulate ? (
                  <Link to="/app/simulators/whatsapp" className="text-sm font-semibold text-accent-ink hover:underline">
                    {t('inbox.simulatorHint')}
                  </Link>
                ) : undefined
              }
            />
          ) : (
            <ul>
              {rows.map((conversation) => (
                <li key={conversation.id}>
                  <ConversationRow
                    conversation={conversation}
                    href={hrefWith({ c: conversation.id })}
                    selected={conversation.id === selected}
                  />
                </li>
              ))}
              {total > rows.length && (
                <li className="p-3 text-center">
                  <Button variant="ghost" size="sm" onClick={() => setLimit((current) => current + PAGE)} loading={conversations.isFetching}>
                    {t('inbox.loadMore')}
                  </Button>
                </li>
              )}
            </ul>
          )}
        </div>
      </nav>
      <div className={cn('min-w-0 flex-1', selected ? 'flex' : 'hidden md:flex')}>
        {selected ? (
          <ConversationPane key={selected} conversationId={selected} backHref={hrefWith({ c: null })} />
        ) : (
          <div className="grid flex-1 place-items-center">
            <EmptyState icon={MessagesSquare} title={t('inbox.selectTitle')} description={t('inbox.selectDescription')} />
          </div>
        )}
      </div>
    </div>
  )
}
