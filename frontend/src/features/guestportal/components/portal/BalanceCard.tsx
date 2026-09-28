import { useMutation } from '@tanstack/react-query'
import { CreditCard, Receipt } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyInput, MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { payBalance, type PortalBalance, type PortalPayment } from '../../api'
import { portalError } from '../../lib/errors'
import { moneyLabel } from '../../lib/money'
import { goTo } from '../../lib/navigation'

/** What the guest owes, what they paid (their receipt) and the way to pay online. */
export function BalanceCard({
  balance,
  payments,
  token,
  primary,
}: {
  balance: PortalBalance
  payments: PortalPayment[]
  token: string
  primary: boolean
}) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [paying, setPaying] = useState(false)
  const due = Number(balance.due)
  const total = Number(balance.total)
  const paid = Number(balance.paid)
  const progress = total > 0 ? Math.min(100, Math.max(0, (paid / total) * 100)) : 0

  return (
    <section aria-labelledby="balance-title" className="rounded-2xl border border-border bg-surface p-5 shadow-xs">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="balance-title" className="text-base font-bold">
            {t('balance.title')}
          </h2>
          <p className="text-sm text-muted">
            {due > 0 ? t('balance.due') : due < 0 ? t('balance.credit') : t('balance.settled')}
          </p>
        </div>
        <p className={cn('num text-[28px] leading-8 font-bold tracking-[-0.03em]', due <= 0 && 'text-success-ink')}>
          <MoneyText value={Math.abs(due)} currency={balance.currency} />
        </p>
      </div>

      {total > 0 && (
        <div className="mt-4">
          <div
            role="meter"
            aria-label={t('balance.progress')}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress)}
            aria-valuetext={t('balance.progressText', { paid: moneyLabel(paid, balance.currency), total: moneyLabel(total, balance.currency) })}
            className="h-1.5 overflow-hidden rounded-full bg-surface-3"
          >
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${progress}%` }} />
          </div>
          <dl className="mt-2 flex justify-between text-[13px] text-muted">
            <div className="flex gap-1">
              <dt>{t('balance.paid')}</dt>
              <dd className="num font-semibold text-fg">{moneyLabel(paid, balance.currency)}</dd>
            </div>
            <div className="flex gap-1">
              <dt>{t('balance.total')}</dt>
              <dd className="num font-semibold text-fg">{moneyLabel(total, balance.currency)}</dd>
            </div>
          </dl>
        </div>
      )}

      {due > 0 &&
        (balance.can_pay ? (
          <Button variant={primary ? 'primary' : 'secondary'} size="lg" className="mt-4 w-full" onClick={() => setPaying(true)}>
            <CreditCard aria-hidden />
            {t('balance.pay', { amount: moneyLabel(due, balance.currency) })}
          </Button>
        ) : (
          <p className="mt-4 rounded-lg bg-surface-2 px-3 py-2 text-sm text-muted">{t('balance.payAtHotel')}</p>
        ))}

      {payments.length > 0 && (
        <details className="group mt-4 border-t border-border pt-3">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-fg [&::-webkit-details-marker]:hidden">
            <Receipt aria-hidden className="size-4 text-muted" />
            {t('balance.payments', { count: payments.length })}
          </summary>
          <ul className="mt-2 grid gap-1.5">
            {payments.map((payment, index) => (
              <li key={`${payment.date}-${index}`} className="flex items-center justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-muted">
                  {formatDate(payment.date, undefined, lang)} · {t(`balance.methods.${payment.method}`, { defaultValue: t('balance.methods.other') })}
                </span>
                <MoneyText value={payment.amount} currency={balance.currency} className="font-semibold" />
              </li>
            ))}
          </ul>
        </details>
      )}

      <PayDialog open={paying} onOpenChange={setPaying} balance={balance} token={token} />
    </section>
  )
}

export function PayDialog({
  open,
  onOpenChange,
  balance,
  token,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  balance: PortalBalance
  token: string
}) {
  const { t } = useTranslation('guestportal')
  const due = Number(balance.due)
  const [amount, setAmount] = useState(String(Math.round(due)))
  const value = Number(amount || 0)
  const valid = value > 0 && value <= due
  const pay = useMutation({
    mutationFn: () => payBalance(token, value === due ? undefined : String(value)),
    onSuccess: (link) => goTo(link.checkout_url),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) setAmount(String(Math.round(due)))
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('balance.payTitle')}</DialogTitle>
          <DialogDescription>{t('balance.payDescription')}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) pay.mutate()
          }}
        >
          <div className="grid gap-1.5">
            <Label htmlFor="portal-pay-amount">{t('balance.amount')}</Label>
            <MoneyInput
              id="portal-pay-amount"
              name="amount"
              value={amount}
              onChange={setAmount}
              currency={balance.currency}
              aria-invalid={!valid}
              aria-describedby="portal-pay-hint"
            />
            <p id="portal-pay-hint" className={cn('text-xs', valid ? 'text-muted' : 'font-medium text-danger-ink')}>
              {t('balance.amountHint', { amount: moneyLabel(due, balance.currency) })}
            </p>
          </div>
          {pay.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {portalError(pay.error, t)}
            </p>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!valid} loading={pay.isPending}>
              {t('balance.goToPay', { amount: moneyLabel(value, balance.currency) })}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
