import { zodResolver } from '@hookform/resolvers/zod'
import { Banknote, CreditCard, Landmark, WalletCards } from 'lucide-react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { recordPayment, useCurrentShift, useFinanceMutation, type ManualPaymentMethod, type Money } from '../api'
import { toNumber } from '../money'

const METHODS: { value: ManualPaymentMethod; icon: typeof Banknote }[] = [
  { value: 'card_terminal', icon: CreditCard },
  { value: 'cash', icon: Banknote },
  { value: 'bank_transfer', icon: Landmark },
  { value: 'other', icon: WalletCards },
]

const schema = z.object({
  amount: z.string().refine((value) => toNumber(value) > 0, 'finance:payment.amountRequired'),
  method: z.enum(['cash', 'card_terminal', 'bank_transfer', 'other']),
  reference: z.string().trim().max(120),
  notes: z.string().trim().max(1000),
})
type Values = z.infer<typeof schema>

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  folioId: string
  suggestedAmount: Money
  currency: string
  onDone?: () => void
}

/** "Registrar pago": money received at the desk (card terminal, cash, transfer, other). */
export function RecordPaymentDialog({ open, onOpenChange, folioId, suggestedAmount, currency, onDone }: Props) {
  const { t } = useTranslation('finance')
  const save = useFinanceMutation((values: Values) => recordPayment(folioId, values), {
    onSuccess: () => {
      toast.success(t('payment.recorded'))
      onOpenChange(false)
      onDone?.()
    },
  })
  return (
    <Dialog open={open} onOpenChange={(next) => !save.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-md">
        <PaymentForm
          defaultAmount={toNumber(suggestedAmount) > 0 ? suggestedAmount : ''}
          currency={currency}
          pending={save.isPending}
          error={save.isError ? errorMessage(save.error, t) : null}
          onSubmit={(values) => save.mutate(values)}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function PaymentForm({
  defaultAmount,
  currency,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  defaultAmount: Money
  currency: string
  pending: boolean
  error: string | null
  onSubmit: (values: Values) => void
  onCancel: () => void
}) {
  const { t } = useTranslation('finance')
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { amount: defaultAmount, method: 'card_terminal', reference: '', notes: '' },
  })
  const method = useWatch({ control: form.control, name: 'method' })
  const shift = useCurrentShift(method === 'cash')
  const needsShift = method === 'cash' && shift.data !== undefined && shift.data.shift === null

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-5" noValidate>
      <DialogHeader>
        <DialogTitle>{t('payment.title')}</DialogTitle>
        <DialogDescription>{t('payment.description')}</DialogDescription>
      </DialogHeader>

      <FormField
        control={form.control}
        name="amount"
        label={t('payment.amount')}
        render={({ field, ...a11y }) => (
          <MoneyInput
            value={field.value}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            currency={currency}
            className="[&_input]:h-11 [&_input]:text-lg [&_input]:font-semibold"
            {...a11y}
          />
        )}
      />

      <FormField
        control={form.control}
        name="method"
        label={t('payment.method')}
        render={({ field, id, ...a11y }) => (
          <ToggleGroup
            id={id}
            type="single"
            aria-label={t('payment.method')}
            value={field.value}
            onValueChange={(value) => value && field.onChange(value)}
            className="grid grid-cols-2 gap-1 sm:grid-cols-4"
            {...a11y}
          >
            {METHODS.map(({ value, icon: Icon }) => (
              <ToggleGroupItem key={value} value={value} className="h-9 w-full">
                <Icon aria-hidden />
                {t(`methods.${value}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
      />

      {needsShift && (
        <div role="alert" className="grid gap-2 rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm text-warning-ink">
          <p>{t('payment.shiftRequired')}</p>
          <Button asChild size="sm" variant="secondary" className="w-fit">
            <Link to="/app/cashier">{t('payment.goToCashier')}</Link>
          </Button>
        </div>
      )}

      <FormField
        control={form.control}
        name="reference"
        label={t(`payment.referenceLabel.${method}`)}
        render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
      />
      <FormField
        control={form.control}
        name="notes"
        label={t('payment.notes')}
        render={({ field, ...a11y }) => <Textarea rows={2} {...field} {...a11y} />}
      />

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {error}
        </p>
      )}

      <DialogFooter>
        <Button variant="secondary" onClick={onCancel} disabled={pending}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={pending}>
          {t('payment.submit')}
        </Button>
      </DialogFooter>
    </form>
  )
}
