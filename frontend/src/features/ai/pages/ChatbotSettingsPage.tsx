import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BedDouble, CircleCheck, ExternalLink, Mail, MessageCircleQuestion, MessagesSquare, Pencil, Phone, Plus, Trash2 } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import {
  aiKeys,
  createFaq,
  deleteFaq,
  resolveConversation,
  updateFaq,
  useConversation,
  useConversations,
  useFaqs,
  type ChatbotConversation,
  type ChatbotConversationDetail,
  type ConversationFilter,
  type FAQ,
  type Lang,
} from '../api'

type Tab = 'faq' | 'conversations'

/** `/app/settings/chatbot`: what the hotel's chatbot answers (FAQ per language) and its conversations. */
export default function ChatbotSettingsPage() {
  const { t } = useTranslation('ai')
  const [params, setParams] = useSearchParams()
  const selected = params.get('conversation')
  const tab: Tab = selected || params.get('tab') === 'conversations' ? 'conversations' : 'faq'
  const open = useConversations('open')
  const openCount = open.data?.count ?? 0

  function setTab(next: string) {
    setParams(next === 'conversations' ? { tab: 'conversations' } : {}, { replace: true })
  }

  return (
    <div>
      <PageHeader title={t('chatbot.title')} description={t('chatbot.description')} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="faq">
            <MessageCircleQuestion aria-hidden />
            {t('chatbot.tabFaq')}
          </TabsTrigger>
          <TabsTrigger value="conversations">
            <MessagesSquare aria-hidden />
            {t('chatbot.tabConversations')}
            {openCount > 0 && (
              <Badge tone="warning" aria-label={t('chatbot.openCount', { count: openCount })}>
                {openCount}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="faq">
          <FaqTab />
        </TabsContent>
        <TabsContent value="conversations">
          <ConversationsTab
            selected={selected}
            onSelect={(id) => setParams(id ? { tab: 'conversations', conversation: id } : { tab: 'conversations' }, { replace: true })}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ---- FAQ -------------------------------------------------------------------------------------------

function FaqTab() {
  const { t, i18n } = useTranslation('ai')
  const [language, setLanguage] = useState<Lang>(normalizeLang(i18n.language))
  const faqs = useFaqs(language)
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<FAQ | 'new' | null>(null)
  const [deleting, setDeleting] = useState<FAQ | null>(null)
  const items = faqs.data?.results ?? []

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['ai', 'faqs'] })
  const toggle = useMutation({
    mutationFn: (faq: FAQ) => updateFaq(faq.id, { is_active: !faq.is_active }),
    onSuccess: () => void invalidate(),
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-muted">{t('chatbot.language')}</span>
          <ToggleGroup type="single" value={language} onValueChange={(value) => value && setLanguage(value as Lang)} aria-label={t('chatbot.language')}>
            <ToggleGroupItem value="es">{t('chatbot.es')}</ToggleGroupItem>
            <ToggleGroupItem value="en">{t('chatbot.en')}</ToggleGroupItem>
          </ToggleGroup>
        </div>
        <Button variant="primary" onClick={() => setEditing('new')}>
          <Plus aria-hidden />
          {t('chatbot.addFaq')}
        </Button>
      </div>

      {faqs.isError ? (
        <ErrorState error={faqs.error} onRetry={() => void faqs.refetch()} />
      ) : faqs.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border-strong bg-surface">
          <EmptyState
            icon={MessageCircleQuestion}
            title={t('chatbot.faqEmptyTitle')}
            description={t('chatbot.faqEmptyText')}
            action={
              <Button size="sm" onClick={() => setEditing('new')}>
                <Plus aria-hidden />
                {t('chatbot.addFaq')}
              </Button>
            }
          />
        </div>
      ) : (
        <ul className="grid gap-3" lang={language}>
          {items.map((faq) => (
            <li key={faq.id} className={cn('rounded-lg border border-border bg-surface px-4 py-3.5 shadow-xs', !faq.is_active && 'bg-surface-2/60')}>
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <p className={cn('font-bold text-fg', !faq.is_active && 'text-muted')}>{faq.question}</p>
                  <p className="mt-1 text-[13.5px] whitespace-pre-line text-muted">{faq.answer}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Switch
                    checked={faq.is_active}
                    aria-label={faq.is_active ? t('chatbot.active') : t('chatbot.inactive')}
                    disabled={toggle.isPending && toggle.variables?.id === faq.id}
                    onCheckedChange={() => toggle.mutate(faq)}
                  />
                  <Button variant="ghost" size="icon-sm" aria-label={t('chatbot.editFaq')} onClick={() => setEditing(faq)}>
                    <Pencil aria-hidden />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={t('chatbot.delete')} onClick={() => setDeleting(faq)}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              </div>
              {!faq.is_active && <p className="mt-2 text-xs text-subtle">{t('chatbot.inactiveHint')}</p>}
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <FaqDialog
          faq={editing === 'new' ? null : editing}
          language={language}
          nextSort={items.reduce((max, faq) => Math.max(max, faq.sort), 0) + 1}
          onClose={() => setEditing(null)}
          onSaved={() => {
            void invalidate()
            setEditing(null)
          }}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(next) => !next && setDeleting(null)}
        title={t('chatbot.deleteTitle')}
        description={deleting ? `${t('chatbot.deleteText')} «${deleting.question}»` : undefined}
        confirmLabel={t('chatbot.delete')}
        onConfirm={async () => {
          if (!deleting) return
          await deleteFaq(deleting.id)
          toast.success(t('chatbot.deleted'))
          setDeleting(null)
          void invalidate()
        }}
      />
    </div>
  )
}

function FaqDialog({
  faq,
  language,
  nextSort,
  onClose,
  onSaved,
}: {
  faq: FAQ | null
  language: Lang
  nextSort: number
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation('ai')
  const questionId = useId()
  const answerId = useId()
  const activeId = useId()
  const [question, setQuestion] = useState(faq?.question ?? '')
  const [answer, setAnswer] = useState(faq?.answer ?? '')
  const [lang, setLang] = useState<Lang>(faq?.language ?? language)
  const [active, setActive] = useState(faq?.is_active ?? true)
  const [problem, setProblem] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () =>
      faq
        ? updateFaq(faq.id, { question: question.trim(), answer: answer.trim(), language: lang, is_active: active })
        : createFaq({ question: question.trim(), answer: answer.trim(), language: lang, is_active: active, sort: nextSort }),
    onSuccess: () => {
      toast.success(t('chatbot.saved'))
      onSaved()
    },
    onError: (error) => setProblem(errorMessage(error, t)),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!question.trim() || !answer.trim()) {
      setProblem(t('chatbot.required'))
      return
    }
    save.mutate()
  }

  return (
    <Dialog open onOpenChange={(next) => !next && !save.isPending && onClose()}>
      <DialogContent className="max-w-xl">
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{faq ? t('chatbot.editFaq') : t('chatbot.addFaq')}</DialogTitle>
            <DialogDescription>{t('chatbot.faqHint')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor={questionId}>{t('chatbot.question')}</Label>
            <Input id={questionId} name="question" maxLength={300} value={question} onChange={(event) => setQuestion(event.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={answerId}>{t('chatbot.answer')}</Label>
            <Textarea id={answerId} name="answer" rows={5} maxLength={2000} value={answer} onChange={(event) => setAnswer(event.target.value)} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ToggleGroup type="single" value={lang} onValueChange={(value) => value && setLang(value as Lang)} aria-label={t('chatbot.language')}>
              <ToggleGroupItem value="es">{t('chatbot.es')}</ToggleGroupItem>
              <ToggleGroupItem value="en">{t('chatbot.en')}</ToggleGroupItem>
            </ToggleGroup>
            <div className="flex items-center gap-2">
              <Switch id={activeId} checked={active} onCheckedChange={setActive} />
              <Label htmlFor={activeId}>{t('chatbot.active')}</Label>
            </div>
          </div>
          {problem && (
            <p role="alert" className="text-[13px] text-danger-ink">
              {problem}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" disabled={save.isPending} onClick={onClose}>
              {t('chatbot.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {t('chatbot.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---- conversations ---------------------------------------------------------------------------------

function ConversationsTab({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const { t } = useTranslation('ai')
  const [filter, setFilter] = useState<ConversationFilter>('all')
  const conversations = useConversations(filter)
  const wide = useMediaQuery('(min-width: 1024px)')
  const items = conversations.data?.results ?? []

  const list = (
    <div className="grid content-start gap-3">
      <ToggleGroup type="single" value={filter} onValueChange={(value) => value && setFilter(value as ConversationFilter)} aria-label={t('chatbot.filter')}>
        <ToggleGroupItem value="all">{t('chatbot.filterAll')}</ToggleGroupItem>
        <ToggleGroupItem value="handoff">{t('chatbot.filterHandoff')}</ToggleGroupItem>
        <ToggleGroupItem value="open">{t('chatbot.filterOpen')}</ToggleGroupItem>
      </ToggleGroup>
      {conversations.isError ? (
        <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />
      ) : conversations.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border-strong bg-surface">
          <EmptyState icon={MessagesSquare} title={t('chatbot.conversationsEmptyTitle')} description={t('chatbot.conversationsEmptyText')} />
        </div>
      ) : (
        <ul className="grid gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <ConversationRow item={item} active={item.id === selected} onSelect={() => onSelect(item.id)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )

  if (wide) {
    return (
      <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        {list}
        <div className="min-w-0 rounded-lg border border-border bg-surface shadow-xs">
          {selected ? (
            <ConversationDetail id={selected} />
          ) : (
            <EmptyState icon={MessagesSquare} title={t('chatbot.selectConversation')} className="py-20" />
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      {list}
      <Sheet open={Boolean(selected)} onOpenChange={(next) => !next && onSelect(null)}>
        <SheetContent side="right" className="w-[min(34rem,100vw)]" aria-describedby={undefined}>
          {selected && <ConversationDetail id={selected} inSheet />}
        </SheetContent>
      </Sheet>
    </>
  )
}

function contactName(item: ChatbotConversation, visitor: string): string {
  return item.contact?.name || visitor
}

function ConversationRow({ item, active, onSelect }: { item: ChatbotConversation; active: boolean; onSelect: () => void }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const pending = item.handoff_requested && !item.handoff_resolved_at
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active || undefined}
      className={cn(
        'grid w-full gap-1.5 rounded-lg border px-3.5 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        active ? 'border-accent/60 bg-accent-soft/50' : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2/60',
      )}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          {pending && <span aria-hidden className="size-2 shrink-0 rounded-full bg-warning" />}
          <span className="truncate font-bold text-fg">{contactName(item, t('chatbot.visitor'))}</span>
        </span>
        {item.last_message_at && <span className="shrink-0 text-xs text-subtle">{formatRelative(item.last_message_at, lang)}</span>}
      </span>
      {item.last_message && <span className="line-clamp-2 text-[13px] text-muted">«{item.last_message}»</span>}
      <span className="flex flex-wrap items-center gap-1.5">
        {pending && <Badge tone="warning">{t('chatbot.handoff')}</Badge>}
        {item.handoff_resolved_at && <Badge tone="success">{t('chatbot.attended')}</Badge>}
        <Badge tone="neutral">{t('chatbot.messages', { count: item.messages_count })}</Badge>
        <Badge tone="outline">{item.language.toUpperCase()}</Badge>
      </span>
    </button>
  )
}

const REASONS: Record<string, string> = {
  requested: 'chatbot.reasonRequested',
  low_confidence: 'chatbot.reasonLow',
  complaint: 'chatbot.reasonComplaint',
}

function ConversationDetail({ id, inSheet = false }: { id: string; inSheet?: boolean }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const conversation = useConversation(id)
  const queryClient = useQueryClient()
  const resolve = useMutation({
    mutationFn: () => resolveConversation(id),
    onSuccess: (data) => {
      queryClient.setQueryData<ChatbotConversationDetail>(aiKeys.conversation(id), data)
      void queryClient.invalidateQueries({ queryKey: ['ai', 'conversations'] })
      toast.success(t('chatbot.resolved'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  if (conversation.isError || conversation.isPending) {
    const state = conversation.isError ? (
      <ErrorState error={conversation.error} onRetry={() => void conversation.refetch()} />
    ) : (
      <LoadingState />
    )
    // Dialogs need a title from the first frame, also while the conversation loads.
    return inSheet ? (
      <>
        <SheetTitle className="sr-only">{t('chatbot.transcript')}</SheetTitle>
        {state}
      </>
    ) : (
      state
    )
  }
  const item = conversation.data
  const name = contactName(item, t('chatbot.visitor'))
  const pending = item.handoff_requested && !item.handoff_resolved_at
  const Title = inSheet ? SheetTitle : 'h2'

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <Title className="text-base font-bold text-fg">{name}</Title>
        <p className="text-xs text-muted">
          {item.last_message_at ? formatRelative(item.last_message_at, lang) : ''} · {t('chatbot.messages', { count: item.messages_count })}
        </p>
      </div>
      {pending ? (
        <Button size="sm" variant="primary" loading={resolve.isPending} onClick={() => resolve.mutate()}>
          <CircleCheck aria-hidden />
          {t('chatbot.resolve')}
        </Button>
      ) : item.handoff_resolved_at ? (
        <Badge tone="success">{t('chatbot.attended')}</Badge>
      ) : null}
    </div>
  )

  const body = (
    <div className="grid gap-5">
      {item.handoff_requested && (
        <section className="grid gap-2 rounded-lg border border-border bg-bg px-4 py-3">
          <p className="eyebrow">{t('chatbot.contact')}</p>
          <p className="text-[13px] text-muted">{t(REASONS[item.handoff_reason] ?? 'chatbot.reasonOther')}</p>
          {item.contact?.name || item.contact?.email || item.contact?.phone ? (
            <ul className="grid gap-1 text-sm">
              {item.contact.name && <li className="font-semibold text-fg">{item.contact.name}</li>}
              {item.contact.email && (
                <li>
                  <a href={`mailto:${item.contact.email}`} className="inline-flex items-center gap-1.5 text-accent-ink underline-offset-2 hover:underline">
                    <Mail aria-hidden className="size-3.5" />
                    {item.contact.email}
                  </a>
                </li>
              )}
              {item.contact.phone && (
                <li>
                  <a href={`tel:${item.contact.phone}`} className="num inline-flex items-center gap-1.5 text-accent-ink underline-offset-2 hover:underline">
                    <Phone aria-hidden className="size-3.5" />
                    {item.contact.phone}
                  </a>
                </li>
              )}
              {item.contact.message && <li className="text-muted">«{item.contact.message}»</li>}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t('chatbot.noContact')}</p>
          )}
          {item.reservation && (
            <Link to={`/app/reservations/${item.reservation.id}`} className="inline-flex w-fit items-center gap-1.5 text-sm font-semibold text-accent-ink hover:underline">
              {t('chatbot.reservation')} {item.reservation.code}
              <ExternalLink aria-hidden className="size-3.5" />
            </Link>
          )}
        </section>
      )}
      <section className="grid gap-3">
        <p className="eyebrow">{t('chatbot.transcript')}</p>
        <ol className="grid gap-3" lang={item.language}>
          {item.messages.map((message, index) => (
            <li key={index} className={cn('flex flex-col gap-1', message.role === 'assistant' ? 'items-end' : 'items-start')}>
              <span className="text-[11px] font-semibold text-subtle">
                {message.role === 'assistant' ? t('chatbot.assistant') : t('chatbot.guest')}
                {message.at && <span className="font-normal"> · {formatRelative(message.at, lang)}</span>}
              </span>
              <p
                className={cn(
                  'max-w-[88%] rounded-2xl px-3.5 py-2 text-[13.5px] whitespace-pre-line',
                  message.role === 'assistant' ? 'rounded-br-md bg-accent-soft text-fg' : 'rounded-bl-md bg-surface-3 text-fg',
                )}
              >
                {message.content}
              </p>
              {message.cards.length > 0 && (
                <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                  <BedDouble aria-hidden className="size-3.5" />
                  {t('chatbot.cards', { count: message.cards.length })}
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )

  if (inSheet) {
    return (
      <>
        <SheetHeader>{header}</SheetHeader>
        <SheetBody>{body}</SheetBody>
      </>
    )
  }
  return (
    <div className="grid gap-5 p-5">
      {header}
      {body}
    </div>
  )
}
