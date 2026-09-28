import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, FileClock, Search, Sparkles, SquarePen } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip } from '@/components/ui/tooltip'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  aiKeys,
  askCopilot,
  createSession,
  useCopilotSession,
  useCopilotSessions,
  useCopilotStatus,
  type CopilotAction,
  type CopilotSessionDetail,
} from '../api'
import { useCopilotStore } from '../store'
import { Markdown } from './Markdown'
import { toTurns } from './turns'
import { ProposalCard } from './ProposalCard'

/** The copilot: a side panel with the conversation, quick suggestions and proposal slips to confirm. */
export function CopilotPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const propertyId = property?.id ?? ''
  const sessionId = useCopilotStore((state) => (propertyId ? (state.sessions[propertyId] ?? null) : null))
  const setSession = useCopilotStore((state) => state.setSession)
  const takePending = useCopilotStore((state) => state.takePending)
  const status = useCopilotStatus(lang, open && Boolean(propertyId))
  const session = useCopilotSession(sessionId)
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [asking, setAsking] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const inputId = useId()
  const endRef = useRef<HTMLDivElement>(null)

  const ask = useMutation({
    mutationFn: async (question: string) => {
      let id = sessionId
      if (!id) {
        const created = await createSession()
        queryClient.setQueryData(aiKeys.session(created.id), created)
        setSession(propertyId, created.id)
        id = created.id
      }
      return askCopilot(id, question, lang)
    },
    onMutate: (question) => {
      setAsking(question)
      setFailure(null)
    },
    onSuccess: (turn) => {
      queryClient.setQueryData<CopilotSessionDetail>(aiKeys.session(turn.session.id), (old) => ({
        ...(old ?? { messages: [], actions: [] }),
        ...turn.session,
        messages: [...(old?.messages ?? []), ...turn.messages],
        actions: [...(old?.actions ?? []), ...turn.proposals],
      }))
      void queryClient.invalidateQueries({ queryKey: aiKeys.sessions() })
    },
    onError: (error) => setFailure(errorMessage(error, t)),
    onSettled: () => setAsking(null),
  })

  // ⌘K "Ask the copilot…" leaves the question in the store: send it as soon as the panel is ready.
  useEffect(() => {
    if (!open || !propertyId) return
    const pending = takePending()
    if (pending) ask.mutate(pending)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run when the panel opens, not on every render
  }, [open, propertyId])

  const turns = useMemo(
    () => toTurns(session.data?.messages ?? [], session.data?.actions ?? []),
    [session.data?.messages, session.data?.actions],
  )

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, asking, session.data?.actions])

  function submit(question = text) {
    const value = question.trim()
    if (!value || ask.isPending || !propertyId) return
    setText('')
    ask.mutate(value)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  function onDecided(action: CopilotAction) {
    if (!sessionId) return
    queryClient.setQueryData<CopilotSessionDetail>(aiKeys.session(sessionId), (old) =>
      old ? { ...old, actions: old.actions.map((item) => (item.id === action.id ? action : item)) } : old,
    )
  }

  function newConversation() {
    if (propertyId) setSession(propertyId, null)
    setFailure(null)
    setText('')
  }

  const disabled = status.data?.enabled === false
  const empty = turns.length === 0 && !asking

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[min(30rem,100vw)] gap-0 bg-bg p-0" aria-describedby={undefined}>
        <header className="flex items-start gap-3 border-b border-border bg-surface px-5 py-4 pr-12">
          <span aria-hidden className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
            <Sparkles className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <SheetTitle>{t('copilot.title')}</SheetTitle>
              {status.data?.effective === 'simulated' && (
                <Tooltip content={t('copilot.simulatedHint')}>
                  <Badge tone="warning" tabIndex={0}>
                    {t('copilot.simulated')}
                  </Badge>
                </Tooltip>
              )}
              {status.data?.effective === 'real' && (
                <Badge tone="success">{t('copilot.live', { provider: status.data.provider_label })}</Badge>
              )}
            </div>
            <SheetDescription className="mt-0.5">{t('copilot.description', { hotel: property?.name ?? '' })}</SheetDescription>
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            <SessionHistory />
            <Tooltip content={t('copilot.newConversation')}>
              <Button variant="ghost" size="icon-sm" aria-label={t('copilot.newConversation')} onClick={newConversation}>
                <SquarePen aria-hidden />
              </Button>
            </Tooltip>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5" aria-live="polite">
          {disabled && <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-muted">{t('copilot.disabled')}</p>}
          {empty && !disabled && (
            <div className="flex h-full flex-col justify-end gap-4 pb-2">
              <div>
                <p className="text-lg font-bold text-fg">{t('copilot.emptyTitle')}</p>
                <p className="mt-1 text-sm text-muted">{t('copilot.emptyText')}</p>
              </div>
              {(status.data?.suggestions ?? []).length > 0 && (
                <ul className="flex flex-col gap-2">
                  {status.data!.suggestions.map((suggestion) => (
                    <li key={suggestion}>
                      <button
                        type="button"
                        onClick={() => submit(suggestion)}
                        className="w-full rounded-lg border border-border bg-surface px-3.5 py-2.5 text-left text-sm font-medium text-fg shadow-xs transition-colors hover:border-border-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                      >
                        {suggestion}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <ol className="flex flex-col gap-6">
            {turns.map((turn) => (
              <li key={turn.key} className="flex flex-col gap-3">
                {turn.question && <Question text={turn.question.content} />}
                {turn.consulted.length > 0 && (
                  <p className="flex items-center gap-1.5 text-xs text-subtle">
                    <Search aria-hidden className="size-3" />
                    {t('copilot.consulted', { tools: turn.consulted.map((name) => t(`tools.${name}`)).join(', ') })}
                  </p>
                )}
                {turn.answers.map((answer) => (
                  <Markdown key={answer.id}>{answer.content}</Markdown>
                ))}
                {status.data?.effective === 'real' && turn.answers.some((answer) => answer.simulated) && (
                  <p className="text-xs text-warning-ink">{t('copilot.fallbackNote')}</p>
                )}
                {turn.actions.map((action) => (
                  <ProposalCard key={action.id} action={action} onDecided={onDecided} />
                ))}
              </li>
            ))}
            {asking && (
              <li className="flex flex-col gap-3">
                <Question text={asking} />
                <Thinking />
              </li>
            )}
          </ol>
          {failure && (
            <p role="alert" className="mt-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {failure}
            </p>
          )}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            submit()
          }}
          className="border-t border-border bg-surface px-4 pt-3 pb-3"
        >
          <label htmlFor={inputId} className="sr-only">
            {t('copilot.inputLabel')}
          </label>
          <div className="flex items-end gap-2">
            <Textarea
              id={inputId}
              name="question"
              rows={1}
              value={text}
              disabled={disabled}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={onKeyDown}
              placeholder={t('copilot.placeholder')}
              className="field-sizing-content max-h-40 min-h-10 resize-none py-2"
            />
            <Button
              type="submit"
              variant="primary"
              size="icon"
              aria-label={t('copilot.send')}
              disabled={disabled || !text.trim() || ask.isPending}
            >
              <ArrowUp aria-hidden />
            </Button>
          </div>
          <p className="mt-1.5 text-[11px] text-subtle">{t('copilot.hint')}</p>
        </form>
      </SheetContent>
    </Sheet>
  )
}

function Question({ text }: { text: string }) {
  return (
    <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-surface-3 px-3.5 py-2 text-sm whitespace-pre-wrap text-fg">
      {text}
    </p>
  )
}

function Thinking() {
  const { t } = useTranslation('ai')
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <span aria-hidden className="flex gap-1">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="size-1.5 rounded-full bg-accent motion-safe:animate-pulse"
            style={{ animationDelay: `${dot * 150}ms` }}
          />
        ))}
      </span>
      {t('copilot.thinking')}
    </p>
  )
}

/** Recent conversations of the user in this hotel. */
function SessionHistory() {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const { property } = useActiveProperty()
  const setSession = useCopilotStore((state) => state.setSession)
  const sessions = useCopilotSessions(open)
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Tooltip content={t('copilot.history')}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={t('copilot.history')}>
            <FileClock aria-hidden />
          </Button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>{t('copilot.history')}</DropdownMenuLabel>
        {(sessions.data?.results ?? []).length === 0 && (
          <p className="px-2 py-2 text-[13px] text-muted">{t('copilot.historyEmpty')}</p>
        )}
        {(sessions.data?.results ?? []).map((item) => (
          <DropdownMenuItem key={item.id} onSelect={() => property && setSession(property.id, item.id)}>
            <span className="flex min-w-0 flex-col">
              <span className={cn('truncate font-medium', !item.title && 'text-muted')}>{item.title || t('copilot.untitled')}</span>
              {item.last_message_at && (
                <span className="text-xs text-subtle">{formatRelative(item.last_message_at, lang)}</span>
              )}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default CopilotPanel
