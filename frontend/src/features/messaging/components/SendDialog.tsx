import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { FileText, Mail, MessageCircle, PenLine, Send, TriangleAlert } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { GuestAvatar } from '@/features/guests/components/GuestAvatar'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  previewTemplate,
  sendToGuest,
  useMessagingMutation,
  useRecipient,
  useTemplates,
  type SendChannel,
  type SendResult,
} from '../api'
import { templateOptions } from '../lib/templates'
import { useDebounced } from '../lib/useDebounced'
import { Segmented } from './Segmented'
import { WhatsAppText } from './WhatsAppText'

type Mode = 'template' | 'text'

export interface SendDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Write about this reservation (to its booker unless `guestId` is given). */
  reservationId?: string
  guestId?: string
  onSent?: (result: SendResult) => void
}

/**
 * "Write to the guest" from a reservation, a guest profile or a web-chat thread: a template or free text by
 * WhatsApp or email, with the message exactly as the guest will receive it. It lands in the inbox, in the
 * guest's conversation on that channel.
 */
export function SendDialog({ open, onOpenChange, reservationId, guestId, onSent }: SendDialogProps) {
  const { t } = useTranslation('messaging')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('send.title')}</DialogTitle>
          <DialogDescription>{t('send.description')}</DialogDescription>
        </DialogHeader>
        {open && <SendForm reservationId={reservationId} guestId={guestId} onSent={onSent} close={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function SendForm({
  reservationId,
  guestId,
  onSent,
  close,
}: Pick<SendDialogProps, 'reservationId' | 'guestId' | 'onSent'> & { close: () => void }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const recipient = useRecipient({ reservation: reservationId, guest: guestId })
  const templates = useTemplates()
  const [chosenChannel, setChosenChannel] = useState<SendChannel | null>(null)
  const [mode, setMode] = useState<Mode>('template')
  const [templateCode, setTemplateCode] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [to, setTo] = useState('')
  const [error, setError] = useState('')

  const addresses = recipient.data?.addresses
  // WhatsApp first when the guest has a usable number: it is how most Colombian guests answer.
  const channel: SendChannel = chosenChannel ?? (addresses && !addresses.whatsapp && addresses.email ? 'email' : 'whatsapp')
  const address = addresses?.[channel] ?? ''
  const needsTo = recipient.isSuccess && !address
  const options = templateOptions(templates.data, lang, channel).filter((option) => option.active)
  const code = options.some((option) => option.code === templateCode) ? templateCode : ''

  const draft = useDebounced({ channel, mode, code, subject: channel === 'email' ? subject : '', body })
  const previewEnabled = draft.mode === 'template' ? Boolean(draft.code) : Boolean(draft.body.trim())
  const preview = useQuery({
    queryKey: ['messaging', 'send-preview', reservationId ?? '', guestId ?? '', draft],
    queryFn: () =>
      previewTemplate({
        channel: draft.channel,
        reservation_id: reservationId ?? null,
        guest_id: guestId ?? null,
        ...(draft.mode === 'template' ? { template_code: draft.code } : { subject: draft.subject, body: draft.body }),
      }),
    enabled: recipient.isSuccess && previewEnabled,
    placeholderData: keepPreviousData,
  })

  const send = useMessagingMutation(
    () =>
      sendToGuest({
        channel,
        reservation_id: reservationId,
        guest_id: guestId,
        to: needsTo ? to.trim() : undefined,
        ...(mode === 'template' ? { template_code: code } : { subject: channel === 'email' ? subject.trim() : '', body: body.trim() }),
      }),
    {
      onSuccess: (result) => {
        const via = t(`channels.${result.message.channel}`)
        if (result.message.status === 'failed') toast.error(t('send.failed', { error: result.message.error }))
        else toast.success(t('send.sent', { channel: via }))
        onSent?.(result)
        close()
      },
    },
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    if (needsTo && !to.trim()) return setError(t('send.toRequired'))
    if (mode === 'template' && !code) return setError(t('send.templateRequired'))
    if (mode === 'text' && !body.trim()) return setError(t('send.bodyRequired'))
    setError('')
    send.mutate(undefined, { onError: (failure) => setError(errorMessage(failure, t)) })
  }

  if (recipient.isPending) return <LoadingState variant="rows" rows={4} />
  if (recipient.isError) return <ErrorState error={recipient.error} onRetry={() => recipient.refetch()} />

  const guest = recipient.data.guest
  const formId = `${ids}-form`

  return (
    <>
      <form id={formId} onSubmit={submit} noValidate className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,17rem)]">
        <div className="grid content-start gap-4">
          {guest && (
            <div className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2.5">
              <GuestAvatar name={guest.full_name} size="sm" />
              <div className="min-w-0">
                <p className="truncate font-semibold">{guest.full_name}</p>
                {recipient.data.reservation && (
                  <p className="num text-[12px] text-muted">{t('simulator.reservation', { code: recipient.data.reservation.code })}</p>
                )}
              </div>
            </div>
          )}

          <div className="grid gap-1.5">
            <p className="text-[13px] font-semibold">{t('send.channel')}</p>
            <Segmented
              label={t('send.channel')}
              value={channel}
              onChange={(value) => {
                setChosenChannel(value)
                setError('')
              }}
              options={[
                { value: 'whatsapp', label: t('channels.whatsapp'), icon: MessageCircle },
                { value: 'email', label: t('channels.email'), icon: Mail },
              ]}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor={`${ids}-to`}>{channel === 'email' ? t('send.toEmail') : t('send.toPhone')}</Label>
            {needsTo ? (
              <>
                <Input
                  id={`${ids}-to`}
                  name="to"
                  type={channel === 'email' ? 'email' : 'tel'}
                  inputMode={channel === 'email' ? 'email' : 'tel'}
                  value={to}
                  onChange={(event) => setTo(event.target.value)}
                  placeholder={channel === 'email' ? t('send.toPlaceholderEmail') : t('simulator.phonePlaceholder')}
                  aria-describedby={`${ids}-to-hint`}
                />
                <p id={`${ids}-to-hint`} className="text-[12px] text-warning-ink">
                  {t('send.noAddress', { what: channel === 'email' ? t('send.noEmail') : t('send.noPhone') })}
                </p>
              </>
            ) : (
              <p id={`${ids}-to`} className="num truncate text-[14px]">
                {address}
              </p>
            )}
          </div>

          <div className="grid gap-1.5">
            <p className="text-[13px] font-semibold">{t('send.what')}</p>
            <Segmented
              label={t('send.what')}
              value={mode}
              onChange={(value) => {
                setMode(value)
                setError('')
              }}
              options={[
                { value: 'template', label: t('send.useTemplate'), icon: FileText },
                { value: 'text', label: t('send.freeText'), icon: PenLine },
              ]}
            />
          </div>

          {mode === 'template' ? (
            <div className="grid gap-1.5">
              <Label htmlFor={`${ids}-template`}>{t('send.useTemplate')}</Label>
              <Select value={code} onValueChange={setTemplateCode} name="template_code">
                <SelectTrigger id={`${ids}-template`}>
                  <SelectValue placeholder={t('send.templatePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {options.map((option) => (
                    <SelectItem key={option.code} value={option.code}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <>
              {channel === 'email' && (
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-subject`}>{t('send.subject')}</Label>
                  <Input id={`${ids}-subject`} name="subject" value={subject} onChange={(event) => setSubject(event.target.value)} />
                </div>
              )}
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-body`}>{t('send.body')}</Label>
                <Textarea
                  id={`${ids}-body`}
                  name="body"
                  rows={6}
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder={t('composer.placeholderReply', { example: '{{guest.first_name}}' })}
                />
              </div>
            </>
          )}
          {error && (
            <p role="alert" className="text-[13px] text-danger-ink">
              {error}
            </p>
          )}
        </div>

        <aside aria-label={t('send.preview')} className="grid content-start gap-2 rounded-xl border border-border bg-surface-2/60 p-3">
          <p className="eyebrow">{t('send.preview')}</p>
          {!previewEnabled || !preview.data ? (
            <p className="text-[13px] text-muted">{preview.isFetching ? t('settings.templates.previewLoading') : t('send.previewEmpty')}</p>
          ) : channel === 'email' ? (
            <div className={cn('grid gap-2 rounded-lg border border-border bg-surface p-3 shadow-xs', preview.isFetching && 'opacity-70')}>
              {preview.data.subject && <p className="text-[13px] font-bold break-words">{preview.data.subject}</p>}
              <p className="max-h-72 overflow-y-auto text-[13px] leading-relaxed break-words whitespace-pre-wrap">{preview.data.text}</p>
            </div>
          ) : (
            <div className={cn('hatch rounded-lg p-2.5', preview.isFetching && 'opacity-70')}>
              <p className="max-h-72 w-fit max-w-full overflow-y-auto rounded-xl rounded-tl-sm bg-surface px-2.5 py-2 text-[13px] leading-snug break-words whitespace-pre-wrap shadow-xs">
                <WhatsAppText text={preview.data.whatsapp} />
              </p>
            </div>
          )}
          {preview.data && preview.data.missing.length > 0 && previewEnabled && (
            <p className="flex items-start gap-1.5 text-[12px] text-warning-ink">
              <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {t('settings.templates.missing', { names: preview.data.missing.join(', ') })}
            </p>
          )}
        </aside>
      </form>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={close}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" form={formId} variant="primary" loading={send.isPending}>
          {!send.isPending && <Send aria-hidden />}
          {t('send.submit')}
        </Button>
      </DialogFooter>
    </>
  )
}
