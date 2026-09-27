import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog, DangerConfirmDialog } from '@/components/ConfirmDialog'
import { MoneyInput } from '@/components/Money'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import {
  completeRefund,
  refundPayment,
  useFinanceMutation,
  voidCharge,
  voidPayment,
  type Charge,
  type Payment,
  type Refund,
} from '../api'
import { moneyLabel, plainAmount, toCents, toNumber } from '../money'

function ReasonField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation('finance')
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{t('risk.reason')}</Label>
      <Textarea
        id={id}
        name="reason"
        rows={2}
        value={value}
        maxLength={1000}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t('risk.reasonPlaceholder')}
      />
    </div>
  )
}

interface BaseProps {
  currency: string
  onOpenChange: (open: boolean) => void
  onDone?: () => void
}

/** Void a charge: it stays on the folio, struck through, and stops counting. Type the amount to confirm. */
export function VoidChargeDialog({ charge, currency, onOpenChange, onDone }: BaseProps & { charge: Charge }) {
  const { t } = useTranslation('finance')
  const [reason, setReason] = useState('')
  const mutation = useFinanceMutation(() => voidCharge(charge.id, reason.trim()), {
    onSuccess: () => {
      toast.success(t('risk.chargeVoided'))
      onDone?.()
    },
  })
  return (
    <DangerConfirmDialog
      open
      onOpenChange={onOpenChange}
      title={t('risk.voidChargeTitle')}
      description={t('risk.voidChargeDescription', { description: charge.description, amount: moneyLabel(charge.total, currency) })}
      confirmLabel={t('risk.voidChargeTitle')}
      confirmText={plainAmount(charge.total, currency)}
      confirmDisabled={!reason.trim()}
      onConfirm={() => mutation.mutateAsync(undefined)}
    >
      <ReasonField value={reason} onChange={setReason} />
      {/* Room nights consume the stay total (reservation_balance), so voiding one does not lower what is owed. */}
      {charge.kind === 'room' && <p className="rounded-md bg-warning-soft px-3 py-2 text-xs text-warning-ink">{t('risk.voidRoomHint')}</p>}
    </DangerConfirmDialog>
  )
}

/** Void a manual payment recorded by mistake (the money never came in). */
export function VoidPaymentDialog({ payment, currency, onOpenChange, onDone }: BaseProps & { payment: Payment }) {
  const { t } = useTranslation('finance')
  const [reason, setReason] = useState('')
  const mutation = useFinanceMutation(() => voidPayment(payment.id, reason.trim()), {
    onSuccess: () => {
      toast.success(t('risk.paymentVoided'))
      onDone?.()
    },
  })
  return (
    <DangerConfirmDialog
      open
      onOpenChange={onOpenChange}
      title={t('risk.voidPaymentTitle')}
      description={t('risk.voidPaymentDescription', { amount: moneyLabel(payment.amount, currency) })}
      confirmLabel={t('risk.voidPaymentTitle')}
      confirmText={plainAmount(payment.amount, currency)}
      confirmDisabled={!reason.trim()}
      onConfirm={() => mutation.mutateAsync(undefined)}
    >
      <ReasonField value={reason} onChange={setReason} />
    </DangerConfirmDialog>
  )
}

/** Give money back: amount ≤ what is left of the payment; type the amount to confirm. */
export function RefundDialog({ payment, currency, onOpenChange, onDone }: BaseProps & { payment: Payment }) {
  const { t } = useTranslation('finance')
  const id = useId()
  const [amount, setAmount] = useState(payment.refundable_amount)
  const [reason, setReason] = useState('')
  const mutation = useFinanceMutation(() => refundPayment(payment.id, amount, reason.trim()), {
    onSuccess: (refund: Refund) => {
      if (refund.status === 'approved') toast.success(t('risk.refundApproved'))
      else if (refund.status === 'pending') toast.warning(t('risk.refundPending'))
      else toast.error(t('risk.refundFailed', { error: refund.error }))
      onDone?.()
    },
  })
  const tooMuch = toCents(amount) > toCents(payment.refundable_amount)
  const hintKey =
    payment.method === 'cash'
      ? 'risk.refundHintCash'
      : payment.provider === 'simulated'
        ? 'risk.refundHintSimulated'
        : payment.method === 'wompi_card'
          ? 'risk.refundHintCard'
          : payment.method.startsWith('wompi_')
            ? 'risk.refundHintTransfer'
            : payment.method === 'ota_collect'
              ? 'risk.refundHintOta'
              : null
  return (
    <DangerConfirmDialog
      open
      onOpenChange={onOpenChange}
      title={t('risk.refundTitle')}
      description={t('risk.refundDescription', {
        amount: moneyLabel(payment.amount, currency),
        method: t(`methods.${payment.method}`),
        refundable: moneyLabel(payment.refundable_amount, currency),
      })}
      confirmLabel={t('risk.refund')}
      confirmText={plainAmount(amount || 0, currency)}
      confirmDisabled={!reason.trim() || toNumber(amount) <= 0 || tooMuch}
      onConfirm={() => mutation.mutateAsync(undefined)}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={id}>{t('risk.refundAmount')}</Label>
        <MoneyInput id={id} name="amount" value={amount} onChange={setAmount} currency={currency} aria-invalid={tooMuch} />
        {tooMuch && (
          <p className="text-xs font-medium text-danger-ink">
            {t('risk.refundTooMuch', { refundable: moneyLabel(payment.refundable_amount, currency) })}
          </p>
        )}
      </div>
      <ReasonField value={reason} onChange={setReason} />
      {hintKey && <p className="rounded-md bg-surface-2 px-3 py-2 text-xs text-muted">{t(hintKey)}</p>}
    </DangerConfirmDialog>
  )
}

/** A pending refund (PSE/Nequi transfer, OTA extranet) was done by hand — or could not be done. */
export function CompleteRefundDialog({ refund, currency, onOpenChange, onDone }: BaseProps & { refund: Refund }) {
  const { t } = useTranslation('finance')
  const ids = useId()
  const [outcome, setOutcome] = useState<'approved' | 'failed'>('approved')
  const [reference, setReference] = useState('')
  const mutation = useFinanceMutation(() => completeRefund(refund.id, outcome, reference.trim()), {
    onSuccess: () => {
      toast.success(t('risk.refundUpdated'))
      onDone?.()
    },
  })
  return (
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title={t('risk.completeTitle')}
      description={refund.instructions || t('risk.completeDescription', { amount: moneyLabel(refund.amount, currency) })}
      confirmLabel={t('risk.completeConfirm')}
      onConfirm={() => mutation.mutateAsync(undefined)}
    >
      <RadioGroup value={outcome} onValueChange={(value) => setOutcome(value as 'approved' | 'failed')} aria-label={t('risk.completeTitle')}>
        <label htmlFor={`${ids}-ok`} className="flex items-center gap-2 text-sm">
          <RadioGroupItem id={`${ids}-ok`} value="approved" />
          {t('risk.completeApproved', { amount: moneyLabel(refund.amount, currency) })}
        </label>
        <label htmlFor={`${ids}-ko`} className="flex items-center gap-2 text-sm">
          <RadioGroupItem id={`${ids}-ko`} value="failed" />
          {t('risk.completeFailed')}
        </label>
      </RadioGroup>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-ref`}>{t('risk.completeReference')}</Label>
        <Input id={`${ids}-ref`} name="reference" value={reference} maxLength={120} onChange={(event) => setReference(event.target.value)} />
      </div>
    </ConfirmDialog>
  )
}
