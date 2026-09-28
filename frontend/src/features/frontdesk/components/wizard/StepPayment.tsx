import { CircleAlert } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MoneyInput, MoneyText } from '@/components/Money'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isExistingGuest } from '@/features/guests/api'
import { useCurrentShift } from '@/features/finance/api'
import { cn } from '@/lib/utils'
import type { ManualMethod, PaymentMode, StepErrors, WizardState } from '../../lib/wizard'
import { FieldError } from './FieldError'

const MODES: PaymentMode[] = ['none', 'payment', 'link']
const METHODS: ManualMethod[] = ['cash', 'card_terminal', 'bank_transfer', 'other']

/** Step 5 — guarantee: nothing yet, a payment taken now (cash, card terminal, transfer) or a payment link. */
export function StepPayment({
  state,
  update,
  errors,
  currency,
  suggested,
  deposit,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
  currency: string
  /** What to charge by default: each room's deposit, else the whole stay ('' until priced). */
  suggested: string
  /** The deposit % of the plans picked (null: none asks; 'mixed': they differ). */
  deposit: number | 'mixed' | null
}) {
  const { t } = useTranslation('frontdesk')
  const ids = { mode: useId(), amount: useId(), amountError: useId(), method: useId(), reference: useId(), send: useId(), tentative: useId() }
  const payment = state.payment
  const shift = useCurrentShift(payment.mode === 'payment' && payment.method === 'cash')
  const email = state.guest && (isExistingGuest(state.guest) ? state.guest.email : state.guest.email)

  function setMode(mode: PaymentMode) {
    update({ payment: { ...payment, mode, amount: payment.amount || suggested } })
  }

  return (
    <div className="grid gap-6">
      <fieldset className="grid gap-2">
        <legend id={ids.mode} className="mb-2 font-semibold text-fg">
          {t('wizard.guarantee')}
        </legend>
        {MODES.map((mode) => (
          <label
            key={mode}
            className={cn(
              'flex cursor-pointer items-start gap-3 rounded-lg border border-border px-4 py-3 transition-colors hover:border-border-strong focus-within:ring-2 focus-within:ring-accent/55',
              payment.mode === mode && 'border-accent bg-accent-soft/40 hover:border-accent',
            )}
          >
            <input
              type="radio"
              name="payment-mode"
              value={mode}
              checked={payment.mode === mode}
              onChange={() => setMode(mode)}
              aria-labelledby={`${ids.mode}-${mode}-title`}
              aria-describedby={`${ids.mode}-${mode}`}
              className="mt-1 size-4 shrink-0 accent-accent"
            />
            <span className="min-w-0">
              <span id={`${ids.mode}-${mode}-title`} className="block font-semibold text-fg">
                {t(`wizard.modes.${mode}`)}
              </span>
              <span id={`${ids.mode}-${mode}`} className="block text-[13px] text-muted">
                {t(`wizard.modes.${mode}Hint`)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      {payment.mode !== 'none' && (
        <div className="grid gap-4 rounded-lg border border-border bg-surface-2/50 p-4">
          <div className="grid gap-2 sm:max-w-xs">
            <Label htmlFor={ids.amount} className="font-semibold">
              {t('wizard.amount')}
            </Label>
            <MoneyInput
              id={ids.amount}
              value={payment.amount}
              onChange={(amount) => update({ payment: { ...payment, amount } })}
              currency={currency}
              aria-invalid={Boolean(errors.amount)}
              aria-describedby={errors.amount ? ids.amountError : undefined}
            />
            {deposit !== null && suggested && (
              <p className="text-xs text-muted">
                {deposit === 'mixed' ? t('wizard.depositMixed') : t('wizard.depositHint', { percent: deposit })}{' '}
                <MoneyText value={suggested} currency={currency} />
              </p>
            )}
            <FieldError id={ids.amountError} error={errors.amount} />
          </div>

          {payment.mode === 'payment' && (
            <>
              <fieldset className="grid gap-2">
                <legend id={ids.method} className="mb-1 text-[13px] font-semibold text-fg">
                  {t('wizard.method')}
                </legend>
                <div className="flex flex-wrap gap-2">
                  {METHODS.map((method) => (
                    <label
                      key={method}
                      className={cn(
                        'inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] font-semibold focus-within:ring-2 focus-within:ring-accent/55',
                        payment.method === method && 'border-accent bg-accent-soft/50',
                      )}
                    >
                      <input
                        type="radio"
                        name="payment-method"
                        value={method}
                        checked={payment.method === method}
                        onChange={() => update({ payment: { ...payment, method } })}
                        className="size-3.5 accent-accent"
                      />
                      {t(`wizard.methods.${method}`)}
                    </label>
                  ))}
                </div>
                <FieldError error={errors.method} />
              </fieldset>
              {payment.method === 'cash' && shift.data && !shift.data.shift && (
                <p className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
                  <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  <span>
                    {t('wizard.noShift')}{' '}
                    <Link to="/app/cashier" className="font-semibold underline underline-offset-4">
                      {t('wizard.goToCashier')}
                    </Link>
                  </span>
                </p>
              )}
              <div className="grid gap-2 sm:max-w-xs">
                <Label htmlFor={ids.reference} className="font-semibold">
                  {t('wizard.reference')}
                </Label>
                <Input
                  id={ids.reference}
                  value={payment.reference}
                  onChange={(event) => update({ payment: { ...payment, reference: event.target.value } })}
                  placeholder={t('wizard.referencePlaceholder')}
                  autoComplete="off"
                />
              </div>
            </>
          )}

          {payment.mode === 'link' && email && (
            <div className="flex items-center gap-2">
              <Checkbox
                id={ids.send}
                checked={payment.sendEmail}
                onCheckedChange={(value) => update({ payment: { ...payment, sendEmail: value === true } })}
              />
              <Label htmlFor={ids.send} className="text-[13px] font-semibold">
                {t('wizard.sendEmail', { email })}
              </Label>
            </div>
          )}
        </div>
      )}

      <div className="flex items-start gap-2 border-t border-border pt-5">
        <Checkbox
          id={ids.tentative}
          checked={state.status === 'tentative'}
          onCheckedChange={(value) => update({ status: value === true ? 'tentative' : 'confirmed' })}
          className="mt-0.5"
        />
        <div>
          <Label htmlFor={ids.tentative} className="font-semibold">
            {t('wizard.tentative')}
          </Label>
          <p className="text-[13px] text-muted">{t('wizard.tentativeHint')}</p>
        </div>
      </div>
    </div>
  )
}
