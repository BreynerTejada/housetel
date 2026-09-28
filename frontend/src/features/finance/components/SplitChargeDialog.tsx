import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { MoneyInput, MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { errorMessage } from '@/lib/errors'
import { splitCharge, useFinanceMutation, type Charge, type FolioSummary } from '../api'
import { fromCents, moneyLabel, toCents } from '../money'

interface FolioChoice {
  folio: FolioSummary
  name: string
}

/**
 * "Dividir cargo" (P4): part of a charge goes to a new line — on this folio or on another folio of the reservation
 * (e.g. half the business dinner to the company). The original is voided with the reason and the two parts add up
 * exactly to it (net and IVA split in proportion).
 */
export function SplitChargeDialog({
  charge,
  currency,
  currentFolio,
  targets,
  onOpenChange,
  onDone,
}: {
  charge: Charge
  currency: string
  currentFolio: FolioChoice
  targets: FolioChoice[]
  onOpenChange: (open: boolean) => void
  onDone?: () => void
}) {
  const { t } = useTranslation('finance')
  const totalCents = toCents(charge.total)
  const [amount, setAmount] = useState(fromCents(Math.round(totalCents / 2 / 100) * 100))
  const [target, setTarget] = useState(targets[0]?.folio.id ?? currentFolio.folio.id)
  const [reason, setReason] = useState('')
  const split = useFinanceMutation(
    () => splitCharge(charge.id, amount, target === currentFolio.folio.id ? null : target, reason.trim()),
    {
      onSuccess: () => {
        toast.success(t('split.done', { description: charge.description }))
        onOpenChange(false)
        onDone?.()
      },
    },
  )
  const partCents = toCents(amount)
  const valid = partCents > 0 && partCents < totalCents
  const targetName = [currentFolio, ...targets].find((choice) => choice.folio.id === target)?.name ?? currentFolio.name

  function submit(event: FormEvent) {
    event.preventDefault()
    if (valid && !split.isPending) split.mutate(undefined)
  }

  return (
    <Dialog open onOpenChange={(next) => !split.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-md" hideClose={split.isPending}>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{t('split.title')}</DialogTitle>
            <DialogDescription>
              {t('split.description', { description: charge.description, total: moneyLabel(charge.total, currency) })}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-1.5">
            <Label htmlFor="split-amount">{t('split.amount')}</Label>
            <div className="flex gap-2">
              <MoneyInput id="split-amount" value={amount} onChange={setAmount} currency={currency} className="flex-1" />
              <Button variant="secondary" onClick={() => setAmount(fromCents(Math.round(totalCents / 2 / 100) * 100))}>
                {t('split.half')}
              </Button>
            </div>
            {!valid && amount !== '' && (
              <p className="text-xs text-danger-ink">{t('split.invalid', { total: moneyLabel(charge.total, currency) })}</p>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="split-target">{t('split.target')}</Label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger id="split-target">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {targets.map((choice) => (
                  <SelectItem key={choice.folio.id} value={choice.folio.id}>
                    {choice.name}
                  </SelectItem>
                ))}
                <SelectItem value={currentFolio.folio.id}>{t('split.sameFolio', { name: currentFolio.name })}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {valid && (
            <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-2/70 p-3 text-[13px]">
              <div>
                <dt className="text-muted">{t('split.stays', { name: currentFolio.name })}</dt>
                <dd className="font-semibold">
                  <MoneyText value={fromCents(totalCents - partCents)} currency={currency} />
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t('split.goes', { name: targetName })}</dt>
                <dd className="font-semibold">
                  <MoneyText value={amount} currency={currency} />
                </dd>
              </div>
            </dl>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="split-reason">{t('split.reason')}</Label>
            <Input
              id="split-reason"
              autoComplete="off"
              maxLength={500}
              value={reason}
              placeholder={t('split.reasonPlaceholder')}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>

          {split.isError && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {errorMessage(split.error, t)}
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={split.isPending}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!valid} loading={split.isPending}>
              {t('split.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
