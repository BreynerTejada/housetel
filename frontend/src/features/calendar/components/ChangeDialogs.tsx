import { ArrowRight, CircleAlert, LoaderCircle } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useModifyPreview, type CalStay } from '../api'
import { diffDays } from '../lib/dates'
import type { ChangePlan, ModifyBody, PlanOption, Step } from '../lib/dnd'
import { pick, placeLabel, signedMoney, type RoomIndex } from '../lib/labels'

export interface ChangeRequest {
  stay: CalStay
  plan: ChangePlan
}

interface DialogProps {
  request: ChangeRequest | null
  index: RoomIndex
  onCancel: () => void
  onConfirm: (request: ChangeRequest, option: PlanOption) => void
}

function modifyBody(option: PlanOption | null): ModifyBody | null {
  const step = option?.steps.find((candidate): candidate is Extract<Step, { op: 'modify' }> => candidate.op === 'modify')
  return step?.body ?? null
}

/** A preview the server refused (409/400) will not work for real either: confirming is pointless. */
function refused(error: unknown): boolean {
  return isApiError(error) && error.status >= 400 && error.status < 500
}

// ---- New dates ------------------------------------------------------------------------------------------

/** "Change the dates?": before and after, the new total from the server and what happens to the room. */
export function DatesDialog({ request, index, onCancel, onConfirm }: DialogProps) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md">
        {request?.plan.primary && <DatesBody request={request} option={request.plan.primary} index={index} onCancel={onCancel} onConfirm={onConfirm} />}
      </DialogContent>
    </Dialog>
  )
}

function DatesBody({ request, option, index, onCancel, onConfirm }: Omit<DialogProps, 'request'> & { request: ChangeRequest; option: PlanOption }) {
  const { t } = useTranslation('calendar')
  const { stay, plan } = request
  const body = modifyBody(option)
  const preview = useModifyPreview(plan.stayId, body)
  const keepsRoom = !option.steps.some((step) => step.op !== 'modify')
  const room = plan.from.roomId ? index.rooms.get(plan.from.roomId)?.number : undefined

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t('dates.title')}</DialogTitle>
        <DialogDescription>
          {stay.guest_name} · {placeLabel(t, index, option.next.roomId, option.next.bedId)}
        </DialogDescription>
      </DialogHeader>

      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <RangeCard label={t('dates.before')} checkin={plan.from.checkin} checkout={plan.from.checkout} />
        <ArrowRight aria-hidden className="size-4 text-subtle" />
        <RangeCard label={t('dates.after')} checkin={option.next.checkin} checkout={option.next.checkout} highlight />
      </div>

      <div className="rounded-lg border border-border px-3.5 py-3 text-[13px]">
        {preview.isPending ? (
          <p role="status" className="flex items-center gap-2 text-muted">
            <LoaderCircle aria-hidden className="size-3.5 animate-spin text-accent" />
            {t('dates.calculating')}
          </p>
        ) : preview.isError ? (
          <p role="alert" className="text-danger-ink">
            {t('dates.previewFailed', { detail: errorMessage(preview.error, t) })}
          </p>
        ) : (
          <dl className="grid grid-cols-[1fr_auto] gap-y-1.5">
            <dt className="text-muted">{t('dates.total')}</dt>
            <dd className="num text-right font-bold text-fg">{formatMoney(preview.data.stay.total_amount)}</dd>
            <dt className="text-muted">{t('dates.difference')}</dt>
            <dd className={cn('num text-right font-semibold', Number(preview.data.difference) > 0 ? 'text-warning-ink' : 'text-success-ink')}>
              {signedMoney(preview.data.difference)}
            </dd>
          </dl>
        )}
      </div>
      <p className="text-xs text-muted">{t('dates.priceNote')}</p>
      {keepsRoom && preview.data?.room_kept === false && (
        <p role="alert" className="flex gap-2 rounded-md bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('dates.roomLost', { room })}
        </p>
      )}

      <DialogFooter>
        <Button onClick={onCancel}>{t('actions.cancel', { ns: 'common' })}</Button>
        <Button variant="primary" disabled={refused(preview.error)} onClick={() => onConfirm(request, option)}>
          {t('dates.confirm')}
        </Button>
      </DialogFooter>
    </>
  )
}

function RangeCard({ label, checkin, checkout, highlight = false }: { label: string; checkin: string; checkout: string; highlight?: boolean }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  return (
    <div className={cn('min-w-0 rounded-lg border px-3 py-2.5', highlight ? 'border-accent/40 bg-accent-soft/60' : 'border-border bg-surface-2/60')}>
      <p className="eyebrow">{label}</p>
      <p className={cn('num mt-0.5 text-[14px] leading-5 font-bold', highlight ? 'text-accent-ink' : 'text-fg')}>{formatDateRange(checkin, checkout, lang)}</p>
      <p className="text-xs text-muted">{t('date.nights', { ns: 'common', count: Math.max(0, diffDays(checkin, checkout)) })}</p>
    </div>
  )
}

// ---- Another category -----------------------------------------------------------------------------------

type Choice = 'upgrade' | 'reprice'

/** Moving into another category: an upgrade at the same price, or changing the category and requoting. */
export function CategoryDialog({ request, index, onCancel, onConfirm }: DialogProps) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md">
        {request && <CategoryBody request={request} index={index} onCancel={onCancel} onConfirm={onConfirm} />}
      </DialogContent>
    </Dialog>
  )
}

function CategoryBody({ request, index, onCancel, onConfirm }: Omit<DialogProps, 'request'> & { request: ChangeRequest }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const { stay, plan } = request
  const [choice, setChoice] = useState<Choice>(plan.upgrade ? 'upgrade' : 'reprice')
  const preview = useModifyPreview(plan.primary ? plan.stayId : null, modifyBody(plan.primary))

  const roomId = (plan.upgrade ?? plan.primary)?.next.roomId ?? null
  const room = roomId ? index.rooms.get(roomId) : undefined
  const toTypeId = room?.roomTypeId ?? plan.primary?.next.roomTypeId ?? stay.room_type_id
  const from = pick(index.roomTypeNames.get(stay.room_type_id), lang)
  const to = pick(index.roomTypeNames.get(toTypeId), lang)
  const option = choice === 'upgrade' ? plan.upgrade : plan.primary

  let repriceHint: ReactNode = t('category.repriceUnavailable')
  if (plan.primary) {
    repriceHint = preview.isPending ? (
      t('dates.calculating')
    ) : preview.isError ? (
      <span className="text-danger-ink">{t('dates.previewFailed', { detail: errorMessage(preview.error, t) })}</span>
    ) : (
      t('category.repriceHint', { total: formatMoney(preview.data.stay.total_amount), difference: signedMoney(preview.data.difference) })
    )
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{room ? t('category.title', { room: room.number }) : t('category.unassignedTitle', { to })}</DialogTitle>
        <DialogDescription>
          {room
            ? t('category.description', { guest: stay.guest_name, from, room: room.number, to })
            : t('category.unassignedDescription', { guest: stay.guest_name, from, to })}
        </DialogDescription>
      </DialogHeader>

      <RadioGroup value={choice} onValueChange={(value) => setChoice(value as Choice)} aria-label={t('category.options')} className="gap-2.5">
        {plan.upgrade && (
          <ChoiceCard value="upgrade" checked={choice === 'upgrade'} label={t('category.upgrade')} hint={t('category.upgradeHint', { from, room: room?.number ?? '' })} />
        )}
        <ChoiceCard
          value="reprice"
          checked={choice === 'reprice'}
          disabled={!plan.primary}
          label={t('category.reprice', { to })}
          hint={repriceHint}
        />
      </RadioGroup>

      <DialogFooter>
        <Button onClick={onCancel}>{t('actions.cancel', { ns: 'common' })}</Button>
        <Button
          variant="primary"
          disabled={!option || (choice === 'reprice' && refused(preview.error))}
          onClick={() => option && onConfirm(request, option)}
        >
          {t('category.confirm')}
        </Button>
      </DialogFooter>
    </>
  )
}

function ChoiceCard({ value, checked, disabled = false, label, hint }: { value: Choice; checked: boolean; disabled?: boolean; label: string; hint: ReactNode }) {
  const id = useId()
  return (
    <div
      className={cn(
        'flex gap-3 rounded-lg border px-3.5 py-3 transition-colors',
        checked ? 'border-accent/50 bg-accent-soft/50' : 'border-border',
        disabled && 'opacity-60',
      )}
    >
      <RadioGroupItem id={id} value={value} disabled={disabled} aria-describedby={`${id}-hint`} className="mt-0.5" />
      <div className="grid gap-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      </div>
    </div>
  )
}
