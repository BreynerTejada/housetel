import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BedDouble, CarFront, Clock3, MessageSquareText, Minus, Plus, Sunrise } from 'lucide-react'
import { useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { MoneyText } from '@/components/Money'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { formatDate, normalizeLang } from '@/lib/format'
import {
  createRequest,
  portalKeys,
  type NewRequest,
  type PortalExtra,
  type PortalSummary,
  type RequestKind,
  type RequestStatus,
} from '../../api'
import { portalError } from '../../lib/errors'
import { tr } from '../../lib/text'

const REQUESTABLE = ['confirmed', 'checked_in']
const STATUS_TONE: Record<RequestStatus, BadgeTone> = { requested: 'warning', approved: 'success', rejected: 'stone', done: 'info' }
const KIND_ICON: Record<Exclude<RequestKind, 'extra'>, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
  late_checkout: Clock3,
  early_checkin: Sunrise,
  transfer: CarFront,
  other: MessageSquareText,
}

function useRequest(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: NewRequest) => createRequest(token, body),
    onSuccess: ({ request: _request, ...summary }) => queryClient.setQueryData(portalKeys.portal(token), summary),
  })
}

// ---- Extras ---------------------------------------------------------------------------------------

export function ExtrasSection({ summary, token }: { summary: PortalSummary; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [chosen, setChosen] = useState<PortalExtra | null>(null)
  if (!summary.extras.length || !REQUESTABLE.includes(summary.reservation.status)) return null

  return (
    <section aria-labelledby="extras-title" className="grid gap-3">
      <div>
        <h2 id="extras-title" className="text-lg font-bold">
          {t('extras.title')}
        </h2>
        <p className="text-sm text-muted">{summary.settings.auto_approve_extras ? t('extras.autoHint') : t('extras.manualHint')}</p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {summary.extras.map((extra) => (
          <li key={extra.id} className="flex items-center gap-3 rounded-xl border border-border bg-surface p-3.5">
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{tr(extra.name, lang)}</p>
              <p className="text-[13px] text-muted">
                <MoneyText value={extra.unit_price} currency={extra.currency} /> {t(`extras.chargeTypes.${extra.charge_type}`)}
                {extra.tax_exempt && <span className="ml-1">· {t('extras.taxExempt')}</span>}
              </p>
            </div>
            <Button size="sm" onClick={() => setChosen(extra)} aria-label={t('extras.addNamed', { name: tr(extra.name, lang) })}>
              <Plus aria-hidden />
              {t('extras.add')}
            </Button>
          </li>
        ))}
      </ul>
      {chosen && (
        <ExtraDialog
          key={chosen.id}
          extra={chosen}
          token={token}
          autoApprove={summary.settings.auto_approve_extras}
          onClose={() => setChosen(null)}
        />
      )}
    </section>
  )
}

function ExtraDialog({ extra, token, autoApprove, onClose }: { extra: PortalExtra; token: string; autoApprove: boolean; onClose: () => void }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [quantity, setQuantity] = useState(extra.default_quantity || 1)
  const request = useRequest(token)
  const name = tr(extra.name, lang)
  const total = Number(extra.unit_price) * quantity

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('extras.dialogTitle', { name })}</DialogTitle>
          <DialogDescription>{autoApprove ? t('extras.autoHint') : t('extras.manualHint')}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            request.mutate(
              { kind: 'extra', extra_id: extra.id, quantity },
              {
                onSuccess: () => {
                  toast.success(autoApprove ? t('extras.added', { name }) : t('extras.requested', { name }))
                  onClose()
                },
              },
            )
          }}
        >
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="extra-quantity">{t('extras.quantity')}</Label>
            <div className="flex items-center gap-1">
              <Button size="icon" aria-label={t('extras.less')} disabled={quantity <= 1} onClick={() => setQuantity((q) => Math.max(1, q - 1))}>
                <Minus aria-hidden />
              </Button>
              <input
                id="extra-quantity"
                name="quantity"
                type="number"
                inputMode="numeric"
                min={1}
                max={99}
                value={quantity}
                onChange={(event) => setQuantity(Math.min(99, Math.max(1, Number(event.target.value) || 1)))}
                className="num h-9 w-14 rounded-md border border-border bg-surface text-center text-sm font-semibold"
              />
              <Button size="icon" aria-label={t('extras.more')} disabled={quantity >= 99} onClick={() => setQuantity((q) => Math.min(99, q + 1))}>
                <Plus aria-hidden />
              </Button>
            </div>
          </div>
          <div className="flex items-baseline justify-between rounded-lg bg-surface-2 px-3 py-2.5">
            <span className="text-sm text-muted">{t('extras.total')}</span>
            <MoneyText value={total} currency={extra.currency} className="text-lg font-bold" />
          </div>
          {request.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {portalError(request.error, t)}
            </p>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={onClose}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={request.isPending}>
              {autoApprove ? t('extras.confirm') : t('extras.confirmRequest')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---- Service requests -----------------------------------------------------------------------------

function hours(from: number, to: number): string[] {
  const list: string[] = []
  for (let hour = from; hour <= to; hour++) list.push(`${String(hour).padStart(2, '0')}:00`)
  return list
}

function hourOf(time: string | null | undefined, fallback: number): number {
  const hour = Number((time ?? '').split(':')[0])
  return Number.isFinite(hour) && time ? hour : fallback
}

export function RequestsSection({ summary, token }: { summary: PortalSummary; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [kind, setKind] = useState<Exclude<RequestKind, 'extra'> | null>(null)
  const open = REQUESTABLE.includes(summary.reservation.status)
  if (!open && !summary.requests.length) return null

  return (
    <section aria-labelledby="requests-title" className="grid gap-3">
      <div>
        <h2 id="requests-title" className="text-lg font-bold">
          {t('requests.title')}
        </h2>
        {open && <p className="text-sm text-muted">{t('requests.hint')}</p>}
      </div>
      {open && (
        <div className="grid grid-cols-2 gap-2">
          {(Object.keys(KIND_ICON) as Exclude<RequestKind, 'extra'>[]).map((item) => {
            const Icon = KIND_ICON[item]
            return (
              <button
                key={item}
                type="button"
                onClick={() => setKind(item)}
                className="flex min-h-12 items-center gap-2.5 rounded-xl border border-border bg-surface px-3.5 py-3 text-left text-sm font-semibold transition-colors hover:border-border-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <Icon aria-hidden className="size-4 shrink-0 text-accent-ink" />
                {t(`requests.kinds.${item}`)}
              </button>
            )
          })}
        </div>
      )}
      {summary.requests.length > 0 && (
        <div className="rounded-xl border border-border bg-surface">
          <h3 className="border-b border-border px-4 py-2.5 text-[13px] font-bold text-muted">{t('requests.mine')}</h3>
          <ul className="divide-y divide-border">
            {summary.requests.map((request) => (
              <li key={request.id} className="grid gap-1 px-4 py-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2 font-semibold">
                    {request.kind === 'extra' ? <BedDouble aria-hidden className="size-4 shrink-0 text-muted" /> : null}
                    <span className="truncate">
                      {request.extra ? `${tr(request.extra.name, lang)} × ${request.quantity}` : t(`requests.kinds.${request.kind}`)}
                      {request.requested_time && ` · ${request.requested_time}`}
                    </span>
                  </span>
                  <Badge tone={STATUS_TONE[request.status]}>{t(`requests.statuses.${request.status}`)}</Badge>
                </div>
                <p className="flex flex-wrap gap-x-2 text-[13px] text-muted">
                  <span>{formatDate(request.created_at, undefined, lang)}</span>
                  {request.price && (
                    <span>
                      · <MoneyText value={request.price} />
                    </span>
                  )}
                </p>
                {request.decision_note && <p className="text-[13px] text-muted">{t('requests.hotelNote', { note: request.decision_note })}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {kind && <RequestDialog key={kind} kind={kind} summary={summary} token={token} onClose={() => setKind(null)} />}
    </section>
  )
}

function RequestDialog({
  kind,
  summary,
  token,
  onClose,
}: {
  kind: Exclude<RequestKind, 'extra'>
  summary: PortalSummary
  token: string
  onClose: () => void
}) {
  const { t } = useTranslation('guestportal')
  const request = useRequest(token)
  const checkOut = hourOf(summary.property.check_out_time, 12)
  const checkIn = hourOf(summary.property.check_in_time, 15)
  const options = kind === 'late_checkout' ? hours(checkOut + 1, 20) : kind === 'early_checkin' ? hours(6, Math.max(6, checkIn - 1)) : []
  const [time, setTime] = useState(options[Math.min(1, options.length - 1)] ?? '')
  const [notes, setNotes] = useState('')
  const needsNotes = kind === 'transfer' || kind === 'other'
  const [touched, setTouched] = useState(false)
  const notesMissing = needsNotes && !notes.trim()

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`requests.kinds.${kind}`)}</DialogTitle>
          <DialogDescription>{t(`requests.hints.${kind}`)}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            setTouched(true)
            if (notesMissing) return
            request.mutate(
              { kind, requested_time: options.length ? time : null, notes: notes.trim() },
              {
                onSuccess: () => {
                  toast.success(t('requests.sent'))
                  onClose()
                },
              },
            )
          }}
        >
          {options.length > 0 && (
            <div className="grid gap-1.5">
              <Label htmlFor="request-time">{kind === 'late_checkout' ? t('requests.lateTime') : t('requests.earlyTime')}</Label>
              <Select name="requested_time" value={time} onValueChange={setTime}>
                <SelectTrigger id="request-time">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {options.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="request-notes">{needsNotes ? t('requests.notes') : t('requests.notesOptional')}</Label>
            <Textarea
              id="request-notes"
              name="notes"
              value={notes}
              maxLength={1000}
              onChange={(event) => setNotes(event.target.value)}
              placeholder={t(`requests.placeholders.${kind}`)}
              aria-invalid={touched && notesMissing}
              aria-describedby={touched && notesMissing ? 'request-notes-error' : undefined}
            />
            {touched && notesMissing && (
              <p id="request-notes-error" className="text-xs font-medium text-danger-ink">
                {t('common:validation.required')}
              </p>
            )}
          </div>
          {request.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {portalError(request.error, t)}
            </p>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={onClose}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={request.isPending}>
              {t('requests.send')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
