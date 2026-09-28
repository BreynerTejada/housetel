import { Banknote, CreditCard, Landmark, WalletCards } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DatePicker } from '@/components/DatePicker'
import { MoneyInput, MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { fromCents, moneyLabel, toCents } from '@/features/finance/money'
import { AR_METHODS, useApplyCredit, useRecordAccountPayment, type ArMethod, type Statement, type StatementItem } from '../api'

const METHOD_ICONS: Record<ArMethod, typeof Landmark> = {
  bank_transfer: Landmark,
  cash: Banknote,
  card_terminal: CreditCard,
  other: WalletCards,
}

type Mode = 'auto' | 'manual'

/**
 * "Registrar pago a cuenta" (`mode="payment"`): money the company paid, applied to the oldest open items or to the
 * ones picked; the rest stays in its favor. `mode="credit"` applies that credit in favor to open items.
 */
export function AccountPaymentDialog({
  open,
  onOpenChange,
  companyId,
  statement,
  mode,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  companyId: string
  statement: Statement
  mode: 'payment' | 'credit'
}) {
  const [pending, setPending] = useState(false)
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-xl" hideClose={pending}>
        {open && (
          <PaymentForm
            companyId={companyId}
            statement={statement}
            mode={mode}
            onPendingChange={setPending}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function itemLabel(item: StatementItem): string {
  return item.invoice?.number || item.reservation?.code || item.label
}

function PaymentForm({
  companyId,
  statement,
  mode,
  onPendingChange,
  onClose,
}: {
  companyId: string
  statement: Statement
  mode: 'payment' | 'credit'
  onPendingChange: (pending: boolean) => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const currency = statement.currency
  const record = useRecordAccountPayment(companyId)
  const apply = useApplyCredit(companyId)
  const creditCents = toCents(statement.totals.unapplied)
  const openCents = toCents(statement.totals.balance)
  const candidates = useMemo(
    () =>
      [...statement.items, ...statement.in_progress].filter(
        (item) => item.folio_status === 'open' && toCents(item.expected_balance) > 0,
      ),
    [statement],
  )
  const [amount, setAmount] = useState(mode === 'payment' && openCents > 0 ? fromCents(openCents) : '')
  const [method, setMethod] = useState<ArMethod>('bank_transfer')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [receivedOn, setReceivedOn] = useState<string | null>(property?.business_date ?? null)
  const [allocation, setAllocation] = useState<Mode>('auto')
  const [picked, setPicked] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const budgetCents = mode === 'payment' ? toCents(amount) : creditCents
  const pickedCents = Object.values(picked).reduce((sum, value) => sum + toCents(value), 0)
  const autoCents = Math.min(budgetCents, openCents)
  const appliedCents = allocation === 'auto' ? autoCents : pickedCents
  const leftCents = budgetCents - appliedCents
  const overBudget = allocation === 'manual' && pickedCents > budgetCents
  const pending = record.isPending || apply.isPending
  const canSubmit =
    !pending &&
    !overBudget &&
    (mode === 'payment' ? budgetCents > 0 : appliedCents > 0) &&
    (allocation === 'auto' || pickedCents > 0 || mode === 'payment')

  function toggle(item: StatementItem, checked: boolean) {
    setPicked((current) => {
      const next = { ...current }
      if (!checked) {
        delete next[item.folio_id]
        return next
      }
      const remaining = Math.max(0, budgetCents - pickedCents)
      next[item.folio_id] = fromCents(Math.min(toCents(item.expected_balance), remaining || toCents(item.expected_balance)))
      return next
    })
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    setError(null)
    onPendingChange(true)
    const allocations =
      allocation === 'manual'
        ? Object.entries(picked)
            .filter(([, value]) => toCents(value) > 0)
            .map(([folio_id, value]) => ({ folio_id, amount: value }))
        : []
    try {
      if (mode === 'payment') {
        await record.mutateAsync({
          amount,
          method,
          reference,
          notes,
          received_on: receivedOn,
          allocations,
          auto_allocate: allocation === 'auto',
        })
        toast.success(
          t('payment.recorded', { amount: moneyLabel(amount, currency), applied: moneyLabel(fromCents(appliedCents), currency) }),
        )
      } else {
        await apply.mutateAsync(allocation === 'auto' ? { auto: true } : { allocations })
        toast.success(t('payment.creditApplied', { amount: moneyLabel(fromCents(appliedCents), currency) }))
      }
      onPendingChange(false)
      onClose()
    } catch (err) {
      onPendingChange(false)
      setError(errorMessage(err, t))
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <DialogHeader>
        <DialogTitle>{mode === 'payment' ? t('payment.title') : t('payment.creditTitle')}</DialogTitle>
        <DialogDescription>
          {mode === 'payment'
            ? t('payment.description', { company: statement.company.legal_name })
            : t('payment.creditDescription', { amount: moneyLabel(statement.totals.unapplied, currency) })}
        </DialogDescription>
      </DialogHeader>

      {mode === 'payment' && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="ar-amount">{t('payment.amount')}</Label>
              <MoneyInput
                id="ar-amount"
                value={amount}
                onChange={setAmount}
                currency={currency}
                className="[&_input]:h-11 [&_input]:text-lg [&_input]:font-semibold"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ar-date">{t('payment.receivedOn')}</Label>
              <DatePicker id="ar-date" value={receivedOn} onChange={setReceivedOn} max={property?.business_date} className="h-11" />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label id="ar-method-label">{t('payment.method')}</Label>
            <ToggleGroup
              type="single"
              aria-labelledby="ar-method-label"
              value={method}
              onValueChange={(value) => value && setMethod(value as ArMethod)}
              className="grid grid-cols-2 gap-1 sm:grid-cols-4"
            >
              {AR_METHODS.map((value) => {
                const Icon = METHOD_ICONS[value]
                return (
                  <ToggleGroupItem key={value} value={value} className="h-9 w-full">
                    <Icon aria-hidden />
                    {t(`methods.${value}`)}
                  </ToggleGroupItem>
                )
              })}
            </ToggleGroup>
            {method === 'cash' && <p className="text-xs text-muted">{t('payment.cashHint')}</p>}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ar-reference">{t('payment.reference')}</Label>
            <Input
              id="ar-reference"
              autoComplete="off"
              placeholder={t('payment.referencePlaceholder')}
              value={reference}
              maxLength={120}
              onChange={(event) => setReference(event.target.value)}
            />
          </div>
        </>
      )}

      <fieldset className="grid min-w-0 gap-3">
        <legend className="mb-1 text-[13px] font-semibold text-fg">{t('payment.applyTo')}</legend>
        <RadioGroup value={allocation} onValueChange={(value) => setAllocation(value as Mode)} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(['auto', 'manual'] as Mode[]).map((value) => (
            <label
              key={value}
              className={cn(
                'flex cursor-pointer gap-2.5 rounded-lg border p-3 text-[13px] transition-colors',
                allocation === value ? 'border-accent/50 bg-accent-soft/60' : 'border-border hover:border-border-strong',
              )}
            >
              <RadioGroupItem value={value} className="mt-0.5" />
              <span className="grid gap-0.5">
                <span className="font-semibold text-fg">{t(`payment.mode.${value}`)}</span>
                <span className="text-xs text-muted">{t(`payment.mode.${value}Hint`)}</span>
              </span>
            </label>
          ))}
        </RadioGroup>

        {allocation === 'manual' && (
          <ul className="grid max-h-72 divide-y divide-border overflow-y-auto rounded-lg border border-border">
            {candidates.length === 0 && <li className="px-3 py-4 text-[13px] text-muted">{t('payment.noItems')}</li>}
            {candidates.map((item) => {
              const checked = item.folio_id in picked
              return (
                <li key={item.folio_id} className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 px-3 py-2.5 sm:grid-cols-[auto_1fr_10rem]">
                  <Checkbox
                    id={`pick-${item.folio_id}`}
                    checked={checked}
                    onCheckedChange={(value) => toggle(item, value === true)}
                  />
                  <label htmlFor={`pick-${item.folio_id}`} className="grid min-w-0 cursor-pointer gap-0.5 text-[13px]">
                    <span className="truncate font-semibold text-fg">
                      <span className="num">{itemLabel(item)}</span>
                      {item.reservation && <span className="font-normal text-muted"> · {item.reservation.guest_name}</span>}
                    </span>
                    <span className="text-xs text-muted">
                      {item.document_date
                        ? t('payment.itemDue', {
                            date: formatDate(item.document_date, undefined, lang),
                            amount: moneyLabel(item.expected_balance, currency),
                          })
                        : t('payment.itemInProgress', { amount: moneyLabel(item.expected_balance, currency) })}
                    </span>
                  </label>
                  {checked && (
                    <MoneyInput
                      aria-label={t('payment.itemAmount', { item: itemLabel(item) })}
                      value={picked[item.folio_id] ?? ''}
                      onChange={(value) => setPicked((current) => ({ ...current, [item.folio_id]: value }))}
                      currency={currency}
                      className="col-span-2 sm:col-span-1"
                    />
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </fieldset>

      <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-2/70 p-3 text-[13px]">
        <div>
          <dt className="text-muted">{t('payment.applied')}</dt>
          <dd className="font-semibold">
            <MoneyText value={fromCents(Math.max(0, appliedCents))} currency={currency} />
          </dd>
        </div>
        <div>
          <dt className="text-muted">{mode === 'payment' ? t('payment.leftInFavor') : t('payment.creditLeft')}</dt>
          <dd className={cn('font-semibold', leftCents < 0 && 'text-danger-ink')}>
            <MoneyText value={fromCents(leftCents)} currency={currency} />
          </dd>
        </div>
      </dl>
      {overBudget && (
        <p role="alert" className="text-[13px] text-danger-ink">
          {t('payment.overBudget')}
        </p>
      )}

      {mode === 'payment' && (
        <div className="grid gap-1.5">
          <Label htmlFor="ar-notes">{t('payment.notes')}</Label>
          <Textarea id="ar-notes" rows={2} value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
        </div>
      )}

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {error}
        </p>
      )}

      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={pending}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" disabled={!canSubmit} loading={pending}>
          {mode === 'payment' ? t('payment.submit') : t('payment.creditSubmit')}
        </Button>
      </DialogFooter>
    </form>
  )
}
