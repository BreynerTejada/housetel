import { useLayoutEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { formatDate, normalizeLang } from '@/lib/format'
import { errorMessage } from '@/lib/errors'
import { useTemplates } from '../api'
import { groupByDay } from '../lib/thread'
import type { ThreadState } from '../lib/useThreadMessages'
import { MessageBubble } from './MessageBubble'

/**
 * The messages of a conversation (`thread = useThreadMessages(id)`), oldest first with a separator per day.
 * It keeps the newest message in view when one arrives, and keeps the reading position when older
 * messages are loaded above. Mount its owner with `key={conversationId}` so switching threads starts fresh.
 */
export function Thread({ thread, label }: { thread: ThreadState; label: string }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const { latest, messages, hasMore, loadOlder, loadingOlder, olderError } = thread
  const templates = useTemplates()
  const scroller = useRef<HTMLDivElement>(null)
  const anchor = useRef<{ height: number; top: number } | null>(null)
  const lastId = messages.at(-1)?.id

  const templateLabels = useMemo(() => {
    const labels: Record<string, string> = {}
    for (const template of templates.data ?? []) labels[template.code] = template.label[lang] || template.code
    return labels
  }, [templates.data, lang])

  // New message at the bottom (or first load): show it.
  useLayoutEffect(() => {
    const element = scroller.current
    if (element && !anchor.current) element.scrollTop = element.scrollHeight
  }, [lastId])

  // Older messages loaded above: keep what the user was reading in place.
  useLayoutEffect(() => {
    const element = scroller.current
    if (element && anchor.current) {
      element.scrollTop = element.scrollHeight - anchor.current.height + anchor.current.top
      anchor.current = null
    }
  }, [messages.length])

  function showOlder() {
    const element = scroller.current
    if (element) anchor.current = { height: element.scrollHeight, top: element.scrollTop }
    void loadOlder()
  }

  if (latest.isPending) return <LoadingState variant="rows" rows={5} className="p-6" />
  if (latest.isError) return <ErrorState error={latest.error} onRetry={() => latest.refetch()} />

  function dayLabel(day: string): string {
    const now = new Date()
    if (day === formatDate(now, 'yyyy-MM-dd')) return t('inbox.today')
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
    if (day === formatDate(yesterday, 'yyyy-MM-dd')) return t('inbox.yesterday')
    return formatDate(day, lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", lang)
  }

  return (
    <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto bg-bg px-3 py-4 sm:px-6">
      {hasMore && (
        <div className="mb-4 flex flex-col items-center gap-1">
          <Button variant="ghost" size="sm" onClick={showOlder} loading={loadingOlder}>
            {t('inbox.olderMessages')}
          </Button>
          {Boolean(olderError) && <p className="text-xs text-danger-ink">{errorMessage(olderError, t)}</p>}
        </div>
      )}
      <ol aria-label={label} className="grid gap-5">
        {groupByDay(messages).map((group) => (
          <li key={group.day} className="grid gap-2.5">
            <p className="sticky top-0 z-10 mx-auto w-fit rounded-full border border-border bg-surface/95 px-3 py-0.5 text-[11px] font-semibold text-muted first-letter:uppercase backdrop-blur">
              {dayLabel(group.day)}
            </p>
            <ol className="grid gap-2">
              {group.items.map((message) => (
                <MessageBubble key={message.id} message={message} templateLabels={templateLabels} />
              ))}
            </ol>
          </li>
        ))}
      </ol>
    </div>
  )
}
