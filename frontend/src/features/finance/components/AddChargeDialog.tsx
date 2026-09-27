import { useQuery } from '@tanstack/react-query'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyInput, MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  financeKeys,
  getChargeOptions,
  postCharge,
  useFinanceMutation,
  type ChargeInput,
  type ExtraOption,
  type ManualChargeKind,
  type TaxOption,
} from '../api'
import { fromCents, toCents, toNumber } from '../money'

const NO_TAX = 'none'

/** Net, tax and total of a line the way the backend computes it (COP rounds to whole pesos). */
function preview(unitNet: number, quantity: number, tax: TaxOption | null) {
  const net = Math.round(unitNet * quantity)
  const taxAmount = tax && !tax.exempt ? Math.round((net * Number(tax.rate)) / 100) : 0
  return { net, tax: taxAmount, total: net + taxAmount }
}

function LinePreview({ unitNet, quantity, tax, currency }: { unitNet: number; quantity: number; tax: TaxOption | null; currency: string }) {
  const { t } = useTranslation('finance')
  const line = preview(unitNet, quantity, tax)
  return (
    <dl className="grid grid-cols-3 gap-2 rounded-lg bg-surface-2 px-4 py-3 text-sm">
      <div>
        <dt className="eyebrow">{t('charge.net')}</dt>
        <dd>
          <MoneyText value={line.net} currency={currency} />
        </dd>
      </div>
      <div>
        <dt className="eyebrow">{tax ? tax.name : t('charge.tax')}</dt>
        <dd>{tax?.exempt ? <Badge tone="info">{t('charge.exempt')}</Badge> : <MoneyText value={line.tax} currency={currency} />}</dd>
      </div>
      <div className="text-right">
        <dt className="eyebrow">{t('charge.total')}</dt>
        <dd className="font-semibold">
          <MoneyText value={line.total} currency={currency} />
        </dd>
      </div>
    </dl>
  )
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  folioId: string
  currency: string
  onDone?: () => void
}

/** "Agregar cargo": an extra from the hotel's catalog or a manual line (fee, adjustment, other). */
export function AddChargeDialog({ open, onOpenChange, folioId, currency, onDone }: Props) {
  const { t } = useTranslation('finance')
  const save = useFinanceMutation((input: ChargeInput) => postCharge(folioId, input), {
    onSuccess: () => {
      toast.success(t('charge.posted'))
      onOpenChange(false)
      onDone?.()
    },
  })
  return (
    <Dialog open={open} onOpenChange={(next) => !save.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <ChargeForm
          folioId={folioId}
          currency={currency}
          pending={save.isPending}
          error={save.isError ? errorMessage(save.error, t) : null}
          onSubmit={(input) => save.mutate(input)}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function ChargeForm({
  folioId,
  currency,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  folioId: string
  currency: string
  pending: boolean
  error: string | null
  onSubmit: (input: ChargeInput) => void
  onCancel: () => void
}) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const options = useQuery({ queryKey: financeKeys.chargeOptions(folioId), queryFn: () => getChargeOptions(folioId) })
  const [tab, setTab] = useState<'extra' | 'manual'>('extra')
  const [extraId, setExtraId] = useState('')
  const [extraQuantity, setExtraQuantity] = useState('1')
  const [kind, setKind] = useState<ManualChargeKind>('fee')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [taxId, setTaxId] = useState(NO_TAX)
  const [credit, setCredit] = useState(false)
  const [touched, setTouched] = useState(false)

  const extras = options.data?.extras ?? []
  const taxes = options.data?.taxes ?? []
  const extra: ExtraOption | undefined = extras.find((item) => item.id === extraId)
  const tax = taxes.find((item) => item.id === taxId) ?? null
  const manualKinds = options.data?.manual_kinds ?? ['extra', 'fee', 'adjustment', 'other']

  function chooseExtra(id: string) {
    setExtraId(id)
    const chosen = extras.find((item) => item.id === id)
    if (chosen) setExtraQuantity(String(chosen.default_quantity))
  }

  const extraValid = Boolean(extra) && Number(extraQuantity) >= 1
  const manualValid = description.trim() !== '' && toNumber(amount) > 0 && Number(quantity) >= 1

  function submit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (tab === 'extra') {
      if (extra && extraValid) onSubmit({ extra_id: extra.id, quantity: Number(extraQuantity) })
      return
    }
    if (!manualValid) return
    const signed = kind === 'adjustment' && credit ? fromCents(-toCents(amount)) : amount
    onSubmit({
      kind,
      description: description.trim(),
      amount: signed,
      quantity: Number(quantity),
      tax_id: taxId === NO_TAX ? null : taxId,
    })
  }

  return (
        <form onSubmit={submit} className="grid gap-5" noValidate>
          <DialogHeader>
            <DialogTitle>{t('charge.title')}</DialogTitle>
            <DialogDescription>{t('charge.description')}</DialogDescription>
          </DialogHeader>

          <Tabs value={tab} onValueChange={(value) => setTab(value as 'extra' | 'manual')}>
            <TabsList>
              <TabsTrigger value="extra">{t('charge.tabExtra')}</TabsTrigger>
              <TabsTrigger value="manual">{t('charge.tabManual')}</TabsTrigger>
            </TabsList>

            <TabsContent value="extra" className="grid gap-4">
              {options.isPending ? (
                <LoadingState variant="rows" rows={3} className="p-0" />
              ) : options.isError ? (
                <ErrorState error={options.error} onRetry={() => options.refetch()} className="py-6" />
              ) : extras.length === 0 ? (
                <EmptyState title={t('charge.noExtras')} description={t('charge.noExtrasHint')} className="py-6" />
              ) : (
                <>
                  <RadioGroup
                    value={extraId}
                    onValueChange={chooseExtra}
                    aria-label={t('charge.tabExtra')}
                    className="max-h-64 gap-1.5 overflow-y-auto pr-1"
                  >
                    {extras.map((item) => {
                      const itemId = `${ids}-extra-${item.id}`
                      return (
                        <label
                          key={item.id}
                          htmlFor={itemId}
                          className={cn(
                            'flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors hover:border-border-strong',
                            item.id === extraId && 'border-accent bg-accent-soft/40',
                          )}
                        >
                          <RadioGroupItem id={itemId} value={item.id} />
                          <span className="min-w-0 flex-1">
                            <span className="block font-semibold text-fg">{item.name[lang] || item.name.es || item.code}</span>
                            <span className="block text-xs text-muted">
                              <MoneyText value={item.price} currency={currency} /> {t(`chargeTypes.${item.charge_type}`)}
                              {item.tax && (item.tax.exempt ? ` · ${t('charge.exempt')}` : ` · ${item.tax.name}`)}
                            </span>
                          </span>
                        </label>
                      )
                    })}
                  </RadioGroup>
                  {touched && !extra && <p className="text-xs font-medium text-danger-ink">{t('charge.pickExtra')}</p>}
                  {extra && (
                    <div className="grid gap-3">
                      <div className="grid max-w-40 gap-1.5">
                        <Label htmlFor={`${ids}-extra-qty`}>{t('charge.quantity')}</Label>
                        <Input
                          id={`${ids}-extra-qty`}
                          name="extra_quantity"
                          type="number"
                          inputMode="numeric"
                          min={1}
                          max={999}
                          value={extraQuantity}
                          onChange={(event) => setExtraQuantity(event.target.value)}
                          className="num"
                        />
                      </div>
                      <LinePreview unitNet={toNumber(extra.unit_price)} quantity={Number(extraQuantity) || 0} tax={extra.tax} currency={currency} />
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="manual" className="grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-kind`}>{t('charge.kind')}</Label>
                  <Select name="kind" value={kind} onValueChange={(value) => setKind(value as ManualChargeKind)}>
                    <SelectTrigger id={`${ids}-kind`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {manualKinds.map((value) => (
                        <SelectItem key={value} value={value}>
                          {t(`kinds.${value}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-tax`}>{t('charge.tax')}</Label>
                  <Select name="tax_id" value={taxId} onValueChange={setTaxId}>
                    <SelectTrigger id={`${ids}-tax`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_TAX}>{t('charge.noTax')}</SelectItem>
                      {taxes.map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-description`}>{t('charge.concept')}</Label>
                <Input
                  id={`${ids}-description`}
                  name="description"
                  value={description}
                  maxLength={255}
                  onChange={(event) => setDescription(event.target.value)}
                  aria-invalid={touched && description.trim() === ''}
                  placeholder={t('charge.conceptPlaceholder')}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-amount`}>{t('charge.unitNet')}</Label>
                  <MoneyInput
                    id={`${ids}-amount`}
                    name="amount"
                    value={amount}
                    onChange={setAmount}
                    currency={currency}
                    aria-invalid={touched && toNumber(amount) <= 0}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-qty`}>{t('charge.quantity')}</Label>
                  <Input
                    id={`${ids}-qty`}
                    name="quantity"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={999}
                    value={quantity}
                    onChange={(event) => setQuantity(event.target.value)}
                    className="num"
                  />
                </div>
              </div>
              {kind === 'adjustment' && (
                <label className="flex items-start gap-3 rounded-lg border border-border px-3 py-2.5 text-sm">
                  <Switch checked={credit} onCheckedChange={setCredit} name="credit" className="mt-0.5" />
                  <span>
                    <span className="block font-semibold text-fg">{t('charge.credit')}</span>
                    <span className="block text-xs text-muted">{t('charge.creditHint')}</span>
                  </span>
                </label>
              )}
              <LinePreview
                unitNet={(kind === 'adjustment' && credit ? -1 : 1) * toNumber(amount)}
                quantity={Number(quantity) || 0}
                tax={tax}
                currency={currency}
              />
            </TabsContent>
          </Tabs>

          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={onCancel} disabled={pending}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={pending} disabled={tab === 'extra' && extras.length === 0}>
              {t('charge.submit')}
            </Button>
          </DialogFooter>
        </form>
  )
}
