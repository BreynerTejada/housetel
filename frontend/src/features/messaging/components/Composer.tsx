import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Lock, PenLine, Send, Sparkles, StickyNote } from 'lucide-react'
import { useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  draftReply,
  isNotFound,
  postReply,
  previewTemplate,
  useMessagingMutation,
  useTemplates,
  type Conversation,
  type Message,
  type SendChannel,
} from '../api'
import { REPLY_CHANNELS } from '../lib/channels'
import { SendDialog } from './SendDialog'

// Once the AI module answered 404 the button stays hidden for the session (kept in the query cache, outside
// the `messaging` keys that every mutation invalidates).
const AI_UNAVAILABLE = ['messaging-ai-draft-unavailable'] as const

type Mode = 'reply' | 'note'

/** Channel whose templates fit a conversation (web chat answers are short: the WhatsApp texts). */
function templateChannel(conversation: Conversation): SendChannel {
  return conversation.channel === 'email' ? 'email' : 'whatsapp'
}

/**
 * Reply box of a conversation: answer on the conversation's channel or leave an internal note, insert a
 * template filled with the guest's data, or ask the AI for a draft (hidden when the AI module is absent).
 */
export function Composer({ conversation, lastInbound }: { conversation: Conversation; lastInbound?: Message }) {
  const { t, i18n } = useTranslation('messaging')
  const ids = useId()
  const canSend = useCan('messaging.send')
  const replyable = REPLY_CHANNELS.has(conversation.channel) && Boolean(conversation.address)
  const [mode, setMode] = useState<Mode>(replyable ? 'reply' : 'note')
  const [body, setBody] = useState('')
  const [subject, setSubject] = useState('')
  const [templateCode, setTemplateCode] = useState('')
  const [aiGenerated, setAiGenerated] = useState(false)
  const [aiNotice, setAiNotice] = useState('')
  const queryClient = useQueryClient()
  const aiUnavailable = useQuery({
    queryKey: AI_UNAVAILABLE,
    queryFn: () => false,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const aiHidden = aiUnavailable.data === true
  const [drafting, setDrafting] = useState(false)
  const [error, setError] = useState('')
  const textarea = useRef<HTMLTextAreaElement>(null)
  const [writing, setWriting] = useState(false)
  const navigate = useNavigate()
  const name = conversation.display_name

  const send = useMessagingMutation(
    () =>
      postReply(conversation.id, {
        body: body.trim(),
        subject: mode === 'reply' && conversation.channel === 'email' ? subject.trim() : '',
        internal: mode === 'note',
        template_code: mode === 'reply' ? templateCode : '',
        ai_generated: mode === 'reply' && aiGenerated,
      }),
    {
      onSuccess: (message) => {
        setBody('')
        setSubject('')
        setTemplateCode('')
        setAiGenerated(false)
        setAiNotice('')
        if (message.channel === 'internal_note') toast.success(t('composer.noteSaved'))
        else if (message.status === 'failed') toast.error(t('composer.failed', { error: message.error }))
        else toast.success(t('composer.sent'))
      },
    },
  )

  if (!canSend) {
    return (
      <p className="flex items-center gap-2 border-t border-border bg-surface px-4 py-3 text-sm text-muted">
        <Lock aria-hidden className="size-4" />
        {t('composer.readOnly')}
      </p>
    )
  }

  const effectiveMode: Mode = replyable ? mode : 'note'
  const isNote = effectiveMode === 'note'

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!body.trim()) {
      setError(t('composer.empty'))
      return
    }
    setError('')
    send.mutate(undefined, {
      onError: (failure) => setError(errorMessage(failure, t)),
    })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      submit()
    }
  }

  async function insertTemplate(code: string) {
    try {
      const preview = await previewTemplate({
        channel: templateChannel(conversation),
        template_code: code,
        conversation_id: conversation.id,
      })
      setBody(preview.markup)
      if (conversation.channel === 'email' && !subject.trim()) setSubject(preview.subject)
      setTemplateCode(code)
      setAiGenerated(false)
      setAiNotice('')
      setMode('reply')
      textarea.current?.focus()
    } catch (failure) {
      toast.error(errorMessage(failure, t))
    }
  }

  async function askAi() {
    if (!lastInbound?.body) {
      toast.info(t('composer.aiNoMessage'))
      return
    }
    setDrafting(true)
    try {
      const draft = await draftReply({
        guest_message: lastInbound.body,
        reservation_code: conversation.reservation?.code,
        language: conversation.guest?.language || normalizeLang(i18n.language),
      })
      setBody(draft.text)
      setTemplateCode('')
      setAiGenerated(true)
      setAiNotice(draft.simulated ? t('composer.aiSimulated') : t('composer.aiReview'))
      setMode('reply')
      textarea.current?.focus()
    } catch (failure) {
      if (isNotFound(failure)) {
        queryClient.setQueryData(AI_UNAVAILABLE, true)
        toast.info(t('composer.aiUnavailable'))
      } else {
        toast.error(errorMessage(failure, t))
      }
    } finally {
      setDrafting(false)
    }
  }

  return (
    <>
      <form
        onSubmit={submit}
        aria-label={t('composer.label', { name })}
        className={cn('grid gap-2 border-t border-border px-3 py-3 sm:px-4', isNote ? 'bg-warning-soft/60' : 'bg-surface')}
        noValidate
      >
        {!replyable && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p className="min-w-0 flex-1 text-[13px] text-muted">
              {!conversation.address
                ? t('composer.anonymizedNotice')
                : conversation.channel === 'web_chat'
                  ? t('composer.webChatNotice')
                  : t('composer.otaNotice')}
            </p>
            {conversation.address && conversation.channel === 'web_chat' && (
              <Button type="button" size="sm" onClick={() => setWriting(true)}>
                <PenLine aria-hidden />
                {t('composer.writeGuest')}
              </Button>
            )}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            value={effectiveMode}
            onValueChange={(value) => value && setMode(value as Mode)}
            aria-label={t('composer.modes')}
          >
            <ToggleGroupItem value="reply" disabled={!replyable}>
              <Send aria-hidden />
              {t('composer.reply')}
            </ToggleGroupItem>
            <ToggleGroupItem value="note">
              <StickyNote aria-hidden />
              {t('composer.note')}
            </ToggleGroupItem>
          </ToggleGroup>
          {!isNote && (
            <>
              <TemplatePicker channel={templateChannel(conversation)} onPick={insertTemplate} />
              {!aiHidden && (
                <Button type="button" variant="ghost" size="sm" onClick={askAi} loading={drafting}>
                  {!drafting && <Sparkles aria-hidden />}
                  {drafting ? t('composer.aiDrafting') : t('composer.ai')}
                </Button>
              )}
            </>
          )}
        </div>
        {!isNote && conversation.channel === 'email' && (
          <div className="grid gap-1">
            <label htmlFor={`${ids}-subject`} className="sr-only">
              {t('composer.subject')}
            </label>
            <Input
              id={`${ids}-subject`}
              name="subject"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              placeholder={`${t('composer.subject')} · ${t('composer.subjectPlaceholder')}`}
            />
          </div>
        )}
        <label htmlFor={`${ids}-body`} className="sr-only">
          {isNote ? t('composer.note') : t('composer.reply')}
        </label>
        <Textarea
          ref={textarea}
          id={`${ids}-body`}
          name="body"
          rows={3}
          value={body}
          onChange={(event) => {
            setBody(event.target.value)
            if (!event.target.value) setTemplateCode('')
          }}
          onKeyDown={onKeyDown}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={error ? `${ids}-error` : undefined}
          placeholder={
            isNote
              ? t('composer.placeholderNote')
              : t('composer.placeholderReply', {
                  example: '{{guest.first_name}}',
                })
          }
          className={cn('max-h-64 min-h-20 resize-y', isNote && 'border-warning/40 bg-surface')}
        />
        {aiNotice && !isNote && (
          <p className="flex items-center gap-1.5 text-[12px] text-muted">
            <Sparkles aria-hidden className="size-3.5" />
            {aiNotice}
          </p>
        )}
        {error && (
          <p id={`${ids}-error`} role="alert" className="text-[13px] text-danger-ink">
            {error}
          </p>
        )}
        <div className="flex items-center justify-between gap-3">
          <span className="hidden text-[12px] text-subtle sm:inline">{t('composer.shortcut')}</span>
          <Button type="submit" variant="primary" size="sm" loading={send.isPending} className="ml-auto">
            {!send.isPending && (isNote ? <StickyNote aria-hidden /> : <Send aria-hidden />)}
            {isNote
              ? t('composer.saveNote')
              : t('composer.sendVia', {
                  channel: t(`channels.${conversation.channel}`),
                })}
          </Button>
        </div>
      </form>
      {conversation.channel === 'web_chat' && (
        <SendDialog
          open={writing}
          onOpenChange={setWriting}
          guestId={conversation.guest?.id}
          reservationId={conversation.reservation?.id}
          onSent={(result) => navigate(`/app/inbox?c=${result.conversation_id}`)}
        />
      )}
    </>
  )
}

function TemplatePicker({ channel, onPick }: { channel: SendChannel; onPick: (code: string) => void }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const templates = useTemplates()
  const options = useMemo(() => {
    const byCode = new Map<string, { code: string; label: string; active: boolean }>()
    for (const template of templates.data ?? []) {
      if (template.channel !== channel) continue
      const current = byCode.get(template.code)
      const label = template.label[lang] || template.code
      byCode.set(template.code, {
        code: template.code,
        label,
        active: (current?.active ?? false) || template.is_active,
      })
    }
    return [...byCode.values()].filter((option) => option.active)
  }, [templates.data, channel, lang])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="sm">
          <FileText aria-hidden />
          {t('composer.template')}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="border-b border-border px-3 py-2.5">
          <p className="text-sm font-semibold">{t('composer.templateTitle')}</p>
          <p className="text-[12px] text-muted">{t('composer.templateHint')}</p>
        </div>
        <ul className="max-h-72 overflow-y-auto p-1">
          {options.length === 0 && <li className="px-3 py-3 text-sm text-muted">{t('composer.noTemplates')}</li>}
          {options.map((option) => (
            <li key={option.code}>
              <button
                type="button"
                className="w-full rounded-md px-2.5 py-2 text-left text-sm hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none"
                onClick={() => {
                  setOpen(false)
                  onPick(option.code)
                }}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
