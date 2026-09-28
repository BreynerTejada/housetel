import { zodResolver } from '@hookform/resolvers/zod'
import { ExternalLink, FlaskConical, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm, type FieldPath } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { isApiError } from '@/lib/api'
import { useMe } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { tokenizeCard, usePaymentMethodSetup, useSavePaymentMethod, type PaymentMethodSetup } from '../api'

function luhn(digits: string): boolean {
  let sum = 0
  for (let i = 0; i < digits.length; i++) {
    let digit = Number(digits[digits.length - 1 - i])
    if (i % 2) {
      digit *= 2
      if (digit > 9) digit -= 9
    }
    sum += digit
  }
  return sum % 10 === 0
}

function parseExpiry(value: string): { month: number; year: number } | null {
  const match = /^\s*(\d{1,2})\s*\/?\s*(\d{2}|\d{4})\s*$/.exec(value)
  if (!match) return null
  const month = Number(match[1])
  const year = Number(match[2]) < 100 ? 2000 + Number(match[2]) : Number(match[2])
  return month >= 1 && month <= 12 ? { month, year } : null
}

const schema = z.object({
  holder: z.string().trim().min(2, 'validation.required'),
  number: z
    .string()
    .transform((value) => value.replace(/\D/g, ''))
    .refine((digits) => digits.length >= 13 && digits.length <= 19 && luhn(digits), 'saas:card.errors.number'),
  expiry: z.string().refine((value) => {
    const parsed = parseExpiry(value)
    if (!parsed) return false
    const now = new Date()
    return parsed.year > now.getFullYear() || (parsed.year === now.getFullYear() && parsed.month >= now.getMonth() + 1)
  }, 'saas:card.errors.expiry'),
  cvc: z.string().regex(/^\d{3,4}$/, 'saas:card.errors.cvc'),
  acceptTerms: z.boolean(),
  acceptData: z.boolean(),
})

type CardInput = z.input<typeof schema>
type CardValues = z.output<typeof schema>

const BACKEND_FIELDS: Record<string, FieldPath<CardInput>> = {
  holder: 'holder',
  number: 'number',
  exp_month: 'expiry',
  exp_year: 'expiry',
  cvc: 'cvc',
}

/** "4242424242424242" → "4242 4242 4242 4242" while typing (Amex: 4-6-5). */
function groupCard(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 19)
  if (/^3[47]/.test(digits)) return [digits.slice(0, 4), digits.slice(4, 10), digits.slice(10, 15)].filter(Boolean).join(' ')
  return digits.replace(/(.{4})/g, '$1 ').trim()
}

/** Add or replace the card Housetel charges the subscription to. */
export function PaymentMethodDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation('saas')
  const setup = usePaymentMethodSetup(open)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('card.title')}</DialogTitle>
          <DialogDescription>{t('card.description')}</DialogDescription>
        </DialogHeader>
        {setup.isPending ? (
          <LoadingState />
        ) : setup.isError ? (
          <ErrorState error={setup.error} onRetry={() => void setup.refetch()} className="py-6" />
        ) : (
          <CardForm setup={setup.data} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function CardForm({ setup, onDone }: { setup: PaymentMethodSetup; onDone: () => void }) {
  const { t } = useTranslation('saas')
  const { data: me } = useMe()
  const save = useSavePaymentMethod()
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<CardInput, unknown, CardValues>({
    resolver: zodResolver(schema),
    mode: 'onTouched',
    defaultValues: { holder: me?.full_name ?? '', number: '', expiry: '', cvc: '', acceptTerms: false, acceptData: false },
  })
  const real = setup.mode === 'real'

  function fillTestCard() {
    const next = new Date().getFullYear() + 3
    form.setValue('number', '4242 4242 4242 4242', { shouldValidate: true })
    form.setValue('expiry', `12/${String(next).slice(2)}`, { shouldValidate: true })
    form.setValue('cvc', '123', { shouldValidate: true })
    if (!form.getValues('holder')) form.setValue('holder', me?.full_name ?? 'Housetel Demo', { shouldValidate: true })
  }

  async function onSubmit(values: CardValues) {
    setFailure(null)
    if (real && !(values.acceptTerms && values.acceptData)) {
      setFailure(t('card.errors.accept'))
      return
    }
    const expiry = parseExpiry(values.expiry)
    if (!expiry) return
    const card = { holder: values.holder.trim(), number: values.number, exp_month: expiry.month, exp_year: expiry.year, cvc: values.cvc }
    try {
      if (setup.mode === 'real') {
        const token = await tokenizeCard(setup, card)
        await save.mutateAsync({
          token,
          acceptance_token: setup.acceptance_token,
          accept_personal_auth: setup.personal_auth_token,
        })
      } else {
        await save.mutateAsync(card)
      }
      toast.success(t('card.saved', { last4: values.number.slice(-4) }))
      onDone()
    } catch (error) {
      if (isApiError(error) && error.fields) {
        for (const [field, messages] of Object.entries(error.fields)) {
          const name = BACKEND_FIELDS[field]
          if (name) form.setError(name, { message: messages[0] })
        }
      }
      setFailure(error instanceof Error && !isApiError(error) ? t('card.errors.tokenize', { reason: error.message }) : errorMessage(error, t))
    }
  }

  const busy = form.formState.isSubmitting || save.isPending

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4" noValidate>
      {real ? (
        <p className="flex items-start gap-2 rounded-md bg-success-soft px-3 py-2 text-sm text-success-ink">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('card.realNote')}
        </p>
      ) : (
        <div className="flex items-start gap-2 rounded-md bg-info-soft px-3 py-2 text-sm text-info-ink">
          <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0" />
          <p>
            {t('card.simulatedNote')}{' '}
            <button type="button" onClick={fillTestCard} className="font-semibold underline underline-offset-4">
              {t('card.useTestCard')}
            </button>
          </p>
        </div>
      )}

      <FormField
        control={form.control}
        name="holder"
        label={t('card.holder')}
        render={({ field, ...a11y }) => <Input autoComplete="cc-name" {...field} {...a11y} />}
      />
      <FormField
        control={form.control}
        name="number"
        label={t('card.number')}
        render={({ field, ...a11y }) => (
          <Input
            inputMode="numeric"
            autoComplete="cc-number"
            placeholder="0000 0000 0000 0000"
            className="num"
            name={field.name}
            ref={field.ref}
            onBlur={field.onBlur}
            value={field.value}
            onChange={(event) => field.onChange(groupCard(event.target.value))}
            {...a11y}
          />
        )}
      />
      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name="expiry"
          label={t('card.expiry')}
          render={({ field, ...a11y }) => (
            <Input inputMode="numeric" autoComplete="cc-exp" placeholder={t('card.expiryPlaceholder')} className="num" {...field} {...a11y} />
          )}
        />
        <FormField
          control={form.control}
          name="cvc"
          label={t('card.cvc')}
          render={({ field, ...a11y }) => (
            <Input inputMode="numeric" autoComplete="cc-csc" maxLength={4} placeholder="123" className="num" {...field} {...a11y} />
          )}
        />
      </div>

      {setup.mode === 'real' && (
        <div className="grid grid-cols-1 gap-2.5 rounded-lg border border-border p-3">
          {(
            [
              ['acceptTerms', 'card.acceptTerms', setup.acceptance_permalink],
              ['acceptData', 'card.acceptData', setup.personal_auth_permalink],
            ] as const
          ).map(([name, labelKey, href]) => (
            <Controller
              key={name}
              control={form.control}
              name={name}
              render={({ field }) => (
                <div className="flex items-start gap-2.5">
                  <Checkbox
                    id={`card-${name}`}
                    name={field.name}
                    checked={field.value}
                    onCheckedChange={(value) => field.onChange(value === true)}
                    className="mt-0.5"
                  />
                  <label htmlFor={`card-${name}`} className="text-sm leading-snug text-muted">
                    {t(labelKey)}{' '}
                    {href && (
                      <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-fg underline underline-offset-4">
                        {t('card.readDocument')}
                        <ExternalLink aria-hidden className="size-3" />
                      </a>
                    )}
                  </label>
                </div>
              )}
            />
          ))}
        </div>
      )}

      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}

      <DialogFooter>
        <Button variant="secondary" onClick={onDone} disabled={busy}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={busy}>
          {t('card.save')}
        </Button>
      </DialogFooter>
    </form>
  )
}
