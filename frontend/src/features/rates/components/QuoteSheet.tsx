import { useMutation } from '@tanstack/react-query'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { DateRangePicker } from '@/components/DatePicker'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { DateRangeValue } from '@/lib/date-ranges'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { postQuote, useRoomTypeOptions, type QuoteRequest, type QuoteResult, type RatePlan } from '../api'
import { addDays } from '../lib/grid-utils'
import { pick } from '../lib/text'

/** Violations that stop a sale: restrictions, invalid dates and nights without price (bookings rejects them). */
const BLOCKING = new Set(['invalid_dates', 'stop_sell', 'cta', 'ctd', 'min_los', 'max_los', 'no_rate'])

export interface QuoteSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  plans: RatePlan[]
  /** Plan shown by the grid (preselected). */
  planId: string | null
  /** Business date of the property: the default arrival. */
  today: string
  currency: string
}

/** Side panel to price a stay with the live rules (`POST /rates/quote/`); it never books anything. */
export function QuoteSheet(props: QuoteSheetProps) {
  const { t } = useTranslation('rates')
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent side="right" className="w-[min(34rem,96vw)]">
        <SheetHeader>
          <SheetTitle>{t('quote.title')}</SheetTitle>
          <SheetDescription>{t('quote.description')}</SheetDescription>
        </SheetHeader>
        {props.open && <QuoteForm {...props} />}
      </SheetContent>
    </Sheet>
  )
}

function QuoteForm({ plans, planId, today, currency }: QuoteSheetProps) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const id = useId()
  const roomTypes = useRoomTypeOptions()
  const [plan, setPlan] = useState(planId ?? plans[0]?.id ?? '')
  const [roomType, setRoomType] = useState<string | null>(null)
  const [dates, setDates] = useState<DateRangeValue | null>({ from: today, to: addDays(today, 2) })
  const [adults, setAdults] = useState('2')
  const [children, setChildren] = useState('')
  const [ages, setAges] = useState('')
  const [promo, setPromo] = useState('')
  const [foreign, setForeign] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const mutation = useMutation({ mutationFn: postQuote })

  const selectedPlan = plans.find((item) => item.id === plan) ?? null
  const sold = (roomTypes.data ?? [])
    .filter((item) => selectedPlan?.room_types.includes(item.id))
    .sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code))
  const roomTypeId = roomType && sold.some((item) => item.id === roomType) ? roomType : (sold[0]?.id ?? '')
  const childCount = Number(children || 0)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const adultCount = Number(adults)
    const childAges = ages
      .split(/[,\s]+/)
      .filter(Boolean)
      .map(Number)
    if (!dates || !roomTypeId || !plan) return setProblem(t('quote.needStay'))
    if (!Number.isInteger(adultCount) || adultCount < 1 || adultCount > 50) return setProblem(t('quote.adultsInvalid'))
    if (!Number.isInteger(childCount) || childCount < 0 || childCount > 50) return setProblem(t('quote.childrenInvalid'))
    if (childAges.some((age) => !Number.isInteger(age) || age < 0 || age > 17) || childAges.length > childCount) {
      return setProblem(t('quote.agesInvalid'))
    }
    setProblem(null)
    const body: QuoteRequest = {
      room_type_id: roomTypeId,
      rate_plan_id: plan,
      checkin: dates.from,
      checkout: dates.to,
      adults: adultCount,
      children: childCount,
      children_ages: childCount > 0 ? childAges : [],
      promo_code: promo.trim().toUpperCase(),
      guest_is_foreign_non_resident: foreign,
    }
    mutation.mutate(body)
  }

  return (
    <SheetBody className="grid content-start gap-5">
      <form onSubmit={submit} noValidate className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id={`${id}-plan`} label={t('grid.plan')}>
            <Select name="quote-plan" value={plan} onValueChange={setPlan}>
              <SelectTrigger id={`${id}-plan`}>
                <SelectValue placeholder={t('grid.choosePlan')} />
              </SelectTrigger>
              <SelectContent>
                {plans.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {pick(item.name, lang)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id={`${id}-room-type`} label={t('plans.families.roomType')}>
            <Select name="quote-room-type" value={roomTypeId} onValueChange={setRoomType}>
              <SelectTrigger id={`${id}-room-type`}>
                <SelectValue placeholder={t('quote.chooseRoomType')} />
              </SelectTrigger>
              <SelectContent>
                {sold.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {pick(item.name, lang)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field id={`${id}-dates`} label={t('quote.dates')}>
          <DateRangePicker id={`${id}-dates`} value={dates} onChange={setDates} today={today} showNights minNights={1} />
        </Field>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field id={`${id}-adults`} label={t('quote.adults')}>
            <Input id={`${id}-adults`} inputMode="numeric" autoComplete="off" value={adults} onChange={(event) => setAdults(event.target.value)} className="num" />
          </Field>
          <Field id={`${id}-children`} label={t('quote.children')}>
            <Input
              id={`${id}-children`}
              inputMode="numeric"
              autoComplete="off"
              placeholder="0"
              value={children}
              onChange={(event) => setChildren(event.target.value)}
              className="num"
            />
          </Field>
          {childCount > 0 && (
            <Field id={`${id}-ages`} label={t('quote.ages')} className="col-span-2 sm:col-span-1">
              <Input id={`${id}-ages`} autoComplete="off" placeholder="5, 9" value={ages} onChange={(event) => setAges(event.target.value)} className="num" />
            </Field>
          )}
        </div>
        {childCount > 0 && <p className="-mt-2 text-xs text-muted">{t('quote.agesHint')}</p>}
        <div className="grid items-end gap-3 sm:grid-cols-2">
          <Field id={`${id}-promo`} label={t('quote.promo')}>
            <Input
              id={`${id}-promo`}
              autoComplete="off"
              value={promo}
              onChange={(event) => setPromo(event.target.value.toUpperCase())}
              className="font-semibold tracking-wide"
            />
          </Field>
          <div className="flex items-start gap-3 pb-1">
            <Switch id={`${id}-foreign`} checked={foreign} onCheckedChange={setForeign} aria-describedby={`${id}-foreign-hint`} className="mt-0.5" />
            <div className="grid gap-0.5">
              <Label htmlFor={`${id}-foreign`}>{t('quote.foreign')}</Label>
              <p id={`${id}-foreign-hint`} className="text-xs text-muted">
                {t('quote.foreignHint')}
              </p>
            </div>
          </div>
        </div>
        {(problem || mutation.isError) && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {problem ?? errorMessage(mutation.error, t)}
          </p>
        )}
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {t('quote.calculate')}
          </Button>
        </div>
      </form>

      {mutation.data && !problem && <QuoteBreakdown quote={mutation.data} currency={currency} />}
    </SheetBody>
  )
}

function Field({ id, label, className, children }: { id: string; label: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn('grid gap-1.5', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

function QuoteBreakdown({ quote, currency }: { quote: QuoteResult; currency: string }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const sellable = quote.restrictions_ok && !quote.violations.some((code) => BLOCKING.has(code))
  const money = (value: string) => formatMoney(value, currency)

  return (
    <section aria-live="polite" className="grid gap-4 border-t border-border pt-4">
      <div
        className={cn(
          'grid gap-1.5 rounded-lg px-3.5 py-3 text-sm',
          sellable ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink',
        )}
      >
        <p className="flex items-center gap-2 font-bold">
          {sellable ? <CircleCheck aria-hidden className="size-4" /> : <CircleAlert aria-hidden className="size-4" />}
          {t(sellable ? 'quote.sellable' : 'quote.notSellable')}
        </p>
        {quote.violations.length > 0 && (
          <ul className="grid gap-0.5 pl-6 text-[13px]">
            {quote.violations.map((code) => (
              <li key={code} className="list-disc">
                {t(`quote.violations.${code}`)}
              </li>
            ))}
          </ul>
        )}
      </div>

      {quote.nights.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <Table aria-label={t('quote.nightsLabel')} className="num text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t('quote.night')}</TableHead>
                <TableHead className="text-right">{t('quote.base')}</TableHead>
                <TableHead className="text-right">{t('quote.extras')}</TableHead>
                <TableHead className="text-right">{t('quote.discount')}</TableHead>
                <TableHead className="text-right">{t('quote.nightTotal')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {quote.nights.map((night) => {
                const extras = Number(night.extra_adults) + Number(night.extra_children)
                return (
                  <TableRow key={night.date}>
                    <TableCell className="py-2 whitespace-nowrap">{formatDate(night.date, 'EEE d MMM', lang)}</TableCell>
                    <TableCell className="py-2 text-right">{money(night.base)}</TableCell>
                    <TableCell className="py-2 text-right">{extras ? money(String(extras)) : '—'}</TableCell>
                    <TableCell className="py-2 text-right">{Number(night.discount) ? `−${money(night.discount)}` : '—'}</TableCell>
                    <TableCell className="py-2 text-right font-semibold">{money(night.total)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="num grid gap-1.5 text-[13px]">
        <dl className="grid">
          <SummaryRow label={t('quote.subtotal')} value={money(quote.subtotal)} />
        </dl>
        {quote.promo_applied && (
          <p className="text-xs text-success-ink">{t('quote.promoApplied', { code: quote.promo_applied, amount: money(quote.discount_total) })}</p>
        )}
        <dl className="grid gap-1.5">
          {quote.taxes.map((tax) => (
            <SummaryRow
              key={tax.code}
              label={`${tax.name} (${formatNumber(Number(tax.rate), lang)} %)`}
              note={tax.exempt ? t('quote.exempt') : tax.included ? t('quote.included') : undefined}
              value={money(tax.amount)}
              muted={tax.included || tax.exempt}
            />
          ))}
          <div className="mt-1 flex items-baseline justify-between border-t border-border pt-2">
            <dt className="text-sm font-bold text-fg">{t('quote.total')}</dt>
            <dd>
              <MoneyText value={quote.total} currency={currency} className="text-lg font-bold text-fg" />
            </dd>
          </div>
        </dl>
      </div>
    </section>
  )
}

function SummaryRow({ label, value, note, muted = false }: { label: string; value: string; note?: string; muted?: boolean }) {
  return (
    <div className={cn('flex items-baseline justify-between gap-3', muted ? 'text-muted' : 'text-fg')}>
      <dt>
        <span>{label}</span>
        {note && <span className="ml-1.5 text-2xs font-semibold tracking-wide uppercase">{note}</span>}
      </dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  )
}
