import { useMemo, useState } from 'react'
import { getMessages, useMessages, type Message } from '../api'

function mergeMessages(older: Message[], latest: Message[]): Message[] {
  const seen = new Set<string>()
  const merged: Message[] = []
  for (const message of [...older, ...latest]) {
    if (seen.has(message.id)) continue
    seen.add(message.id)
    merged.push(message)
  }
  return merged
}

/** Hook of a thread: the latest page (polled) plus the older pages the user asked for. */
export function useThreadMessages(conversationId: string) {
  const latest = useMessages(conversationId)
  const [older, setOlder] = useState<Message[]>([])
  const [olderHasMore, setOlderHasMore] = useState<boolean | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [olderError, setOlderError] = useState<unknown>(null)
  const messages = useMemo(() => mergeMessages(older, latest.data?.results ?? []), [older, latest.data])
  const hasMore = olderHasMore ?? latest.data?.has_more ?? false

  async function loadOlder() {
    const first = messages[0]
    if (!first) return
    setLoadingOlder(true)
    setOlderError(null)
    try {
      const page = await getMessages(conversationId, { before: first.created_at })
      setOlder((current) => [...page.results, ...current])
      setOlderHasMore(page.has_more)
    } catch (error) {
      setOlderError(error)
    } finally {
      setLoadingOlder(false)
    }
  }

  return { latest, messages, hasMore, loadOlder, loadingOlder, olderError }
}

export type ThreadState = ReturnType<typeof useThreadMessages>
