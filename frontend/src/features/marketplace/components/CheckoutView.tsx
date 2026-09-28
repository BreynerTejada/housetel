import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, BadgePercent, ChevronDown, CircleAlert, LockKeyhole, ShieldCheck, X } from 'lucide-react'
import { useMemo, useRef, useState, type ReactNode } from 'react'
import { Controller, useForm, useWatch, type Path } from 'react-hook-form'
import { Trans, useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useChatOffset } from '@/features/ai/lib/chat-offset'
import { CountrySelect } from '@/features/guests/components/CountrySelect'
import { LegalLink } from '@/features/saas/components/LegalLink'
import { isApiError, type ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import {
  postBooking,
  useCheckoutQuote,
  useProperty,
  type BookingRequest,
  type CheckoutQuote,
  type CheckoutRequest,
  type ExtraInfo,
  type PaymentOption,
  type PropertyDetail,
  type Via,
} from '../api'
import { hotelHref } from '../lib/links'
import { goToPayment } from '../lib/navigation'
import { parseStay, type Stay } from '../lib/search-params'
import { parseItems, type SelectionItem } from '../lib/selection'
import { rememberBookingEmail } from '../lib/storage'
import { isForeignNonResident } from '../lib/tax'
import { guestsLabel, moneyLabel, tr } from '../lib/text'
import { Photo } from './Cards'
import { PolicyLine } from './RoomTypeCard'

const DOCUMENT_TYPES = ['CC', 'CE', 'PA', 'PPT', 'PEP', 'TI', 'DNI', 'NIT', 'OTHER'] as const
const NONE = 'none'
const ETA_HOURS = Array.from({ length: 13 }, (_, index) => `${String(index + 11).padStart(2, '0')}:00`)
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const SELECTION_ERRORS = ['invalid_room_type', 'invalid_rate_plan', 'capacity_exceeded', 'restriction_violation', 'no_rate', 'too_soon', 'too_far', 'stay_too_long', 'invalid_dates', 'not_found', 'booking_engine_disabled']

const schema = z
  .object({
    first_name: z.string().trim().min(1, 'validation.required'),
    last_name: z.string().trim().min(1, 'validation.required'),
    email: z.string().trim().min(1, 'validation.required').refine((value) => EMAIL.test(value), 'validation.email'),
    phone: z
      .string()
      .trim()
      .min(1, 'validation.required')
      .refine((value) => value.replace(/\D/g, '').length >= 7, 'marketplace:checkout.errors.phone'),
    nationality: z.string().length(2, 'validation.required'),
    country_of_residence: z.string().length(2, 'validation.required'),
    document_type: z.string(),
    document_number: z.string().trim().max(40),
    eta: z.string(),
    special_requests: z.string().max(1000),
    payment_option: z.enum(['pay_now', 'pay_at_hotel']),
    data_processing_consent: z.boolean().refine((value) => value, 'marketplace:checkout.consent.dataRequired'),
    marketing_consent: z.boolean(),
  })
  .superRefine((values, context) => {
    if (values.document_number && values.document_type === NONE) {
      context.addIssue({ code: 'custom', path: ['document_type'], message: 'validation.required' })
    }
  })

type Values = z.infer<typeof schema>

const DEFAULTS: Values = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  nationality: '',
  country_of_residence: '',
  document_type: NONE,
  document_number: '',
  eta: NONE,
  special_requests: '',
  payment_option: 'pay_at_hotel',
  data_processing_consent: false,
  marketing_consent: false,
}

function checkoutItems(items: SelectionItem[], stay: Stay) {
  return items.map((item) => ({
    room_type_id: item.roomTypeId,
    rate_plan_id: item.ratePlanId,
    quantity: item.quantity,
    adults: stay.adults,
    children: stay.children,
    children_ages: stay.ages,
  }))
}

function FormSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="border-t border-border pt-7 first:border-t-0 first:pt-0">
      <h2 className="text-lg font-bold tracking-[-0.01em] text-fg">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

interface CheckoutViewProps {
  slug: string
  via: Via
}

/**
 * Checkout of an online booking (marketplace `/book/:slug` or booking engine `/h/:slug/book`): guest details,
 * extras, arrival, payment option and consent, with an exact quote from the backend that follows every change
 * (nationality and residence decide the IVA exemption of lodging).
 */
export function CheckoutView({ slug, via }: CheckoutViewProps) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const stay = useMemo(() => parseStay(params), [params])
  const items = useMemo(() => parseItems(params.get('items')), [params])
  const detail = useProperty(slug, via)
  const [promo, setPromo] = useState(() => (params.get('promo') ?? '').trim().toUpperCase())
  const [promoDraft, setPromoDraft] = useState('')
  const [promoRejected, setPromoRejected] = useState('')
  const [extras, setExtras] = useState<string[]>([])
  const [blocking, setBlocking] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: DEFAULTS })
  const [nationality, residence, chosenPayment] = useWatch({ control: form.control, name: ['nationality', 'country_of_residence', 'payment_option'] })
  const exempt = isForeignNonResident(nationality, residence)
  // Without live online payments (production without a configured gateway, or the hotel turned them off) the
  // only option is to pay at the hotel, whatever was picked before.
  const hotelTakesOnlinePayments = detail.data?.booking.online_payments ?? true
  const paymentOption: PaymentOption = hotelTakesOnlinePayments ? chosenPayment : 'pay_at_hotel'

  const hasSelection = Boolean(stay.checkin && stay.checkout && items.length > 0)
  const quoteBody = useMemo<CheckoutRequest | null>(
    () =>
      hasSelection
        ? {
            property_slug: slug,
            via,
            checkin: stay.checkin!,
            checkout: stay.checkout!,
            items: checkoutItems(items, stay),
            extras: extras.map((id) => ({ extra_id: id, quantity: null })),
            promo_code: promo,
            payment_option: paymentOption,
            guest: { nationality, country_of_residence: residence },
          }
        : null,
    [hasSelection, slug, via, stay, items, extras, promo, paymentOption, nationality, residence],
  )
  const quote = useCheckoutQuote(quoteBody)
  const actionBar = useRef<HTMLDivElement>(null)
  const phone = !useMediaQuery('(min-width: 1024px)')
  useChatOffset(actionBar, phone && hasSelection && detail.isSuccess)

  // A code that does not apply is dropped (the guest sees why) and the booking is quoted without it.
  const quoteError = isApiError(quote.error) ? quote.error : null
  if (quoteError?.code === 'promo_invalid' && promo) {
    setPromoRejected(promo)
    setPromo('')
  }

  const backHref = hotelHref(slug, stay, via)
  if (detail.isPending) return <LoadingState className="min-h-[60vh]" />
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} className="min-h-[60vh] justify-center" />
  const hotel = detail.data

  const selectionError = blocking ?? (quoteError && quoteError.code !== 'promo_invalid' ? quoteError : null)
  const current: CheckoutQuote | undefined = quote.data
  const dueNow = current ? Number(current.due_now[paymentOption]) : 0
  const onlinePayments = hotelTakesOnlinePayments && (current?.online_payments ?? true)

  async function submit(values: Values) {
    if (!quoteBody) return
    setSubmitting(true)
    const body: BookingRequest = {
      ...quoteBody,
      payment_option: onlinePayments ? values.payment_option : 'pay_at_hotel',
      guest: {
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        phone: values.phone,
        nationality: values.nationality,
        country_of_residence: values.country_of_residence,
        document_type: values.document_number && values.document_type !== NONE ? values.document_type : '',
        document_number: values.document_number,
        data_processing_consent: values.data_processing_consent,
        marketing_consent: values.marketing_consent,
      },
      special_requests: values.special_requests,
      eta: values.eta === NONE ? null : values.eta,
      language: lang,
    }
    try {
      const result = await postBooking(body)
      rememberBookingEmail(result.reservation_code, values.email)
      if (result.payment) {
        goToPayment(result.payment.checkout_url)
        return
      }
      navigate(result.confirmation_path, { state: { email: values.email } })
    } catch (error) {
      setSubmitting(false)
      if (!isApiError(error)) throw error
      if (error.code === 'promo_invalid') {
        setPromoRejected(promo)
        setPromo('')
        return
      }
      const guestFields = (error.fields?.guest ?? null) as unknown as Record<string, string[]> | null
      if (error.code === 'validation_error' && guestFields) {
        for (const [field, messages] of Object.entries(guestFields)) {
          form.setError(field as Path<Values>, { message: messages[0] })
        }
        toast.error(t('checkout.errors.fields'))
        return
      }
      if (error.status === 409 || SELECTION_ERRORS.includes(error.code)) {
        setBlocking(error)
        window.scrollTo({ top: 0, behavior: 'smooth' })
        return
      }
      toast.error(errorMessage(error, t))
    }
  }

  function applyPromo() {
    const code = promoDraft.trim().toUpperCase()
    if (!code) return
    setPromoRejected('')
    setPromo(code)
    setPromoDraft('')
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pt-6 pb-20 sm:px-6">
      <Link to={backHref} className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-fg">
        <ArrowLeft aria-hidden className="size-4" />
        {t('checkout.back', { hotel: hotel.name })}
      </Link>
      <h1 className="mt-4 text-4xl leading-none font-extrabold tracking-[-0.04em] text-fg sm:text-5xl">{t('checkout.title')}</h1>

      {!hasSelection ? (
        <Blocking title={t('checkout.errors.invalidSelectionTitle')} body={t('checkout.errors.invalidSelectionBody')} href={backHref} />
      ) : (
        <div className="mt-6 grid gap-8 lg:mt-8 lg:grid-cols-[minmax(0,1fr)_23rem] lg:gap-12">
          {/* Phones: the total first (the full summary folds out), not after the whole form. */}
          <details className="group overflow-hidden rounded-2xl border border-border bg-surface shadow-xs lg:hidden">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold text-fg">{hotel.name}</span>
                <span className="num block text-xs text-muted">
                  {formatDateRange(stay.checkin, stay.checkout, lang)} · {guestsLabel(stay.adults, stay.children, t)}
                </span>
              </span>
              <span className="text-right">
                <span className="eyebrow block">{t('checkout.summary.total')}</span>
                {current ? (
                  <MoneyText value={current.total} currency={hotel.currency} className="text-lg font-extrabold tracking-[-0.02em] text-fg" />
                ) : (
                  <span className="text-sm text-muted">…</span>
                )}
              </span>
              <ChevronDown aria-hidden className="size-4 shrink-0 text-muted transition-transform group-open:rotate-180" />
              <span className="sr-only">{t('checkout.summary.toggle')}</span>
            </summary>
            <div className="border-t border-border">
              <Summary hotel={hotel} stay={stay} quote={current} updating={quote.isFetching} exempt={Boolean(current?.tax_exempt)} paymentOption={paymentOption} bare />
            </div>
          </details>

          <form onSubmit={form.handleSubmit(submit)} noValidate className="grid min-w-0 gap-8">
            {selectionError && (
              <Blocking
                title={selectionError.code === 'no_availability' ? t('checkout.errors.noAvailabilityTitle') : t('checkout.errors.invalidSelectionTitle')}
                body={selectionError.code === 'no_availability' ? t('checkout.errors.noAvailabilityBody') : errorMessage(selectionError, t)}
                href={backHref}
              />
            )}

            <FormSection title={t('checkout.guest.title')}>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField control={form.control} name="first_name" label={t('checkout.guest.firstName')} render={({ field, ...a11y }) => <Input {...field} {...a11y} autoComplete="given-name" />} />
                <FormField control={form.control} name="last_name" label={t('checkout.guest.lastName')} render={({ field, ...a11y }) => <Input {...field} {...a11y} autoComplete="family-name" />} />
                <FormField
                  control={form.control}
                  name="email"
                  label={t('checkout.guest.email')}
                  description={t('checkout.guest.emailHint')}
                  render={({ field, ...a11y }) => <Input {...field} {...a11y} type="email" autoComplete="email" inputMode="email" />}
                />
                <FormField
                  control={form.control}
                  name="phone"
                  label={t('checkout.guest.phone')}
                  description={t('checkout.guest.phoneHint')}
                  render={({ field, ...a11y }) => <Input {...field} {...a11y} type="tel" autoComplete="tel" inputMode="tel" />}
                />
                <FormField
                  control={form.control}
                  name="nationality"
                  label={t('checkout.guest.nationality')}
                  render={({ field, id, ...a11y }) => (
                    <CountrySelect id={id} value={field.value} onChange={field.onChange} placeholder={t('checkout.guest.chooseCountry')} aria-invalid={a11y['aria-invalid']} />
                  )}
                />
                <FormField
                  control={form.control}
                  name="country_of_residence"
                  label={t('checkout.guest.residence')}
                  render={({ field, id, ...a11y }) => (
                    <CountrySelect id={id} value={field.value} onChange={field.onChange} placeholder={t('checkout.guest.chooseCountry')} aria-invalid={a11y['aria-invalid']} />
                  )}
                />
                <FormField
                  control={form.control}
                  name="document_type"
                  label={t('checkout.guest.documentType')}
                  render={({ field, id, ...a11y }) => (
                    <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id={id} {...a11y}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>{t('checkout.guest.documentNone')}</SelectItem>
                        {DOCUMENT_TYPES.map((type) => (
                          <SelectItem key={type} value={type}>
                            {t(`checkout.docTypes.${type}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <FormField
                  control={form.control}
                  name="document_number"
                  label={t('checkout.guest.documentNumber')}
                  description={t('checkout.guest.documentHint')}
                  render={({ field, ...a11y }) => <Input {...field} {...a11y} autoComplete="off" />}
                />
              </div>
              <ExemptionNote exempt={exempt} />
            </FormSection>

            {hotel.extras.length > 0 && (
              <FormSection title={t('checkout.extras.title')} description={t('checkout.extras.subtitle')}>
                <ul className="grid gap-2">
                  {hotel.extras.map((extra) => (
                    <ExtraOption
                      key={extra.id}
                      extra={extra}
                      currency={hotel.currency}
                      checked={extras.includes(extra.id)}
                      quoted={current?.extras.find((line) => line.extra_id === extra.id)}
                      onChange={(checked) => setExtras((list) => (checked ? [...list, extra.id] : list.filter((id) => id !== extra.id)))}
                    />
                  ))}
                </ul>
              </FormSection>
            )}

            <FormSection title={t('checkout.arrival.title')}>
              <div className="grid gap-4 sm:grid-cols-[14rem_minmax(0,1fr)]">
                <FormField
                  control={form.control}
                  name="eta"
                  label={t('checkout.arrival.eta')}
                  description={hotel.check_in_time ? t('checkout.arrival.etaHint', { time: hotel.check_in_time }) : undefined}
                  render={({ field, id, ...a11y }) => (
                    <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id={id} {...a11y}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>{t('checkout.arrival.etaUnknown')}</SelectItem>
                        {ETA_HOURS.map((hour) => (
                          <SelectItem key={hour} value={hour}>
                            {hour}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <FormField
                  control={form.control}
                  name="special_requests"
                  label={t('checkout.arrival.requests')}
                  description={t('checkout.arrival.requestsHint')}
                  render={({ field, ...a11y }) => <Textarea {...field} {...a11y} rows={3} maxLength={1000} placeholder={t('checkout.arrival.requestsPlaceholder')} />}
                />
              </div>
            </FormSection>

            {(hotel.booking.show_promo_field || promo || promoRejected) && (
              <FormSection title={t('checkout.promo.title')}>
                {promo ? (
                  <p className="flex items-center gap-2 text-sm font-semibold text-success-ink">
                    <BadgePercent aria-hidden className="size-4" />
                    {t('checkout.promo.applied', { code: promo })}
                    <Button variant="ghost" size="icon-sm" aria-label={t('checkout.promo.remove')} onClick={() => setPromo('')}>
                      <X aria-hidden />
                    </Button>
                  </p>
                ) : (
                  <div className="flex max-w-sm gap-2">
                    <Input
                      aria-label={t('checkout.promo.title')}
                      value={promoDraft}
                      onChange={(event) => setPromoDraft(event.target.value.toUpperCase())}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault()
                          applyPromo()
                        }
                      }}
                      placeholder={t('checkout.promo.placeholder')}
                      className="uppercase placeholder:normal-case"
                    />
                    <Button onClick={applyPromo}>{t('checkout.promo.apply')}</Button>
                  </div>
                )}
                {promoRejected && (
                  <p role="alert" className="mt-2 text-sm font-medium text-danger-ink">
                    {t('hotel.stay.promoInvalid', { code: promoRejected })}
                  </p>
                )}
              </FormSection>
            )}

            <FormSection title={t('checkout.payment.title')}>
              {onlinePayments ? (
                <Controller
                  control={form.control}
                  name="payment_option"
                  render={({ field }) => (
                    <RadioGroup name={field.name} value={field.value} onValueChange={(value) => field.onChange(value as PaymentOption)} className="gap-3">
                      <PaymentChoice value="pay_now" title={t('checkout.payment.payNow')} checked={field.value === 'pay_now'}>
                        {t('checkout.payment.payNowBody', { amount: moneyLabel(current?.due_now.pay_now, hotel.currency) })}
                      </PaymentChoice>
                      <PaymentChoice value="pay_at_hotel" title={t('checkout.payment.payAtHotel')} checked={field.value === 'pay_at_hotel'}>
                        {current && Number(current.due_now.pay_at_hotel) > 0
                          ? t('checkout.payment.payDepositBody', { amount: moneyLabel(current.due_now.pay_at_hotel, hotel.currency) })
                          : t('checkout.payment.payAtHotelBody')}
                      </PaymentChoice>
                    </RadioGroup>
                  )}
                />
              ) : (
                <div className="grid gap-3">
                  <RadioGroup name="payment_option" value="pay_at_hotel" className="gap-3" aria-describedby="payment-offline-note">
                    <PaymentChoice value="pay_at_hotel" title={t('checkout.payment.payAtHotel')} checked>
                      {t('checkout.payment.payAtHotelBody')}
                    </PaymentChoice>
                  </RadioGroup>
                  <p id="payment-offline-note" className="text-sm text-muted">
                    {t('checkout.payment.offline')}
                  </p>
                </div>
              )}
              {onlinePayments && (
                <p className="mt-3 flex items-start gap-2 text-xs text-muted">
                  <LockKeyhole aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  {t('checkout.payment.secure')}
                </p>
              )}
            </FormSection>

            <FormSection title={t('checkout.consent.title')}>
              <div className="grid gap-3">
                <ConsentField
                  form={form}
                  name="data_processing_consent"
                  label={
                    <Trans
                      t={t}
                      i18nKey="checkout.consent.data"
                      values={{ hotel: hotel.name }}
                      components={{ privacy: <LegalLink to="/legal/privacidad" /> }}
                    />
                  }
                />
                <ConsentField form={form} name="marketing_consent" label={t('checkout.consent.marketing', { hotel: hotel.name })} />
              </div>
              {tr(hotel.terms, lang) && (
                <details className="mt-4 rounded-xl border border-border bg-surface px-4 py-3 text-sm">
                  <summary className="cursor-pointer font-semibold text-fg">{t('checkout.consent.terms')}</summary>
                  <p className="mt-2 leading-relaxed whitespace-pre-line text-muted">{tr(hotel.terms, lang)}</p>
                </details>
              )}
            </FormSection>

            <div className="border-t border-border pt-7">
              <p className="text-xs text-muted">
                <Trans t={t} i18nKey="checkout.legal" components={{ terms: <LegalLink to="/legal/terminos" /> }} />
              </p>
            </div>
            {/* Phones: the total stays glued to the confirm button while the whole form scrolls under it (a direct
                child of the form, so it sticks from the first field to the last). */}
            <div
              ref={actionBar}
              className="sticky bottom-0 z-10 -mx-4 -mt-5 grid gap-2 border-t border-border bg-bg/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none"
            >
              {current && (
                <p className="flex items-baseline justify-between gap-3 text-sm lg:hidden" aria-live="polite">
                  <span className="text-muted">
                    {t('checkout.summary.total')}
                    {dueNow > 0 && Number(current.total) !== dueNow && <> · {t('checkout.summary.dueNowShort', { amount: moneyLabel(dueNow, hotel.currency) })}</>}
                  </span>
                  <MoneyText value={current.total} currency={hotel.currency} className="text-lg font-extrabold tracking-[-0.02em] text-fg" />
                </p>
              )}
              <Button type="submit" variant="primary" size="lg" className="h-12 w-full text-base lg:w-fit lg:px-8" loading={submitting} disabled={Boolean(selectionError) || !current}>
                {dueNow > 0 ? t('checkout.submitPay', { amount: moneyLabel(dueNow, hotel.currency) }) : t('checkout.submit')}
              </Button>
            </div>
          </form>

          <aside aria-label={t('checkout.summary.title')} className="hidden lg:order-last lg:block">
            <div className="lg:sticky lg:top-24">
              <Summary hotel={hotel} stay={stay} quote={current} updating={quote.isFetching} exempt={Boolean(current?.tax_exempt)} paymentOption={paymentOption} />
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}

function Blocking({ title, body, href }: { title: string; body: string; href: string }) {
  const { t } = useTranslation('marketplace')
  return (
    <div role="alert" className="mt-6 flex flex-col items-start gap-3 rounded-2xl border border-danger/35 bg-danger-soft px-5 py-4 sm:flex-row sm:items-center">
      <CircleAlert aria-hidden className="size-5 shrink-0 text-danger-ink" />
      <div className="flex-1">
        <p className="font-bold text-danger-ink">{title}</p>
        <p className="text-sm text-fg/85">{body}</p>
      </div>
      <Button asChild>
        <Link to={href}>{t('checkout.errors.backToHotel')}</Link>
      </Button>
    </div>
  )
}

function ExemptionNote({ exempt }: { exempt: boolean }) {
  const { t } = useTranslation('marketplace')
  if (!exempt) return <p className="mt-4 text-sm text-muted">{t('checkout.exempt.taxed')}</p>
  return (
    <div role="status" className="mt-4 flex items-start gap-3 rounded-xl bg-success-soft px-4 py-3">
      <ShieldCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-success-ink" />
      <div>
        <p className="font-bold text-success-ink">{t('checkout.exempt.title')}</p>
        <p className="text-sm text-fg/85">{t('checkout.exempt.body')}</p>
      </div>
    </div>
  )
}

function ExtraOption({
  extra,
  currency,
  checked,
  quoted,
  onChange,
}: {
  extra: ExtraInfo
  currency: string
  checked: boolean
  quoted: CheckoutQuote['extras'][number] | undefined
  onChange: (checked: boolean) => void
}) {
  const { t, i18n } = useTranslation('marketplace')
  return (
    <li>
      <label
        className={cn(
          'flex cursor-pointer items-start gap-3 rounded-xl border bg-surface px-4 py-3 transition-colors',
          checked ? 'border-accent bg-accent-soft/40' : 'border-border hover:border-border-strong',
        )}
      >
        <Checkbox checked={checked} onCheckedChange={(value) => onChange(value === true)} className="mt-0.5" />
        <span className="min-w-0 flex-1">
          <span className="block font-semibold text-fg">{tr(extra.name, i18n.language)}</span>
          <span className="block text-sm text-muted">
            {moneyLabel(extra.price, currency)} {t(`checkout.extras.${extra.charge_type}`)}
            {extra.tax_rate && !extra.tax_included && ` ${t('checkout.extras.plusTax', { rate: Number(extra.tax_rate) })}`}
          </span>
        </span>
        {checked && quoted && (
          <span className="text-right text-sm">
            <MoneyText value={quoted.total} currency={currency} className="font-semibold" />
            <span className="block text-xs text-muted">{t('checkout.extras.line', { quantity: quoted.quantity, price: moneyLabel(quoted.unit_price, currency) })}</span>
          </span>
        )}
      </label>
    </li>
  )
}

function PaymentChoice({ value, title, checked, children }: { value: PaymentOption; title: string; checked: boolean; children: ReactNode }) {
  return (
    <Label
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-xl border bg-surface px-4 py-3.5 font-normal transition-colors',
        checked ? 'border-accent bg-accent-soft/40' : 'border-border hover:border-border-strong',
      )}
    >
      <RadioGroupItem value={value} className="mt-0.5" />
      <span>
        <span className="block text-[15px] font-bold text-fg">{title}</span>
        <span className="block text-sm text-muted">{children}</span>
      </span>
    </Label>
  )
}

function ConsentField({ form, name, label }: { form: ReturnType<typeof useForm<Values>>; name: 'data_processing_consent' | 'marketing_consent'; label: ReactNode }) {
  const { t } = useTranslation()
  return (
    <Controller
      control={form.control}
      name={name}
      render={({ field, fieldState }) => (
        <div>
          <label className="flex cursor-pointer items-start gap-3 text-sm text-fg">
            <Checkbox
              name={field.name}
              checked={field.value}
              onCheckedChange={(value) => field.onChange(value === true)}
              aria-invalid={Boolean(fieldState.error)}
              className="mt-0.5"
            />
            <span>{label}</span>
          </label>
          {fieldState.error?.message && (
            <p className="mt-1 ml-7 text-xs font-medium text-danger-ink" aria-live="polite">
              {t(fieldState.error.message)}
            </p>
          )}
        </div>
      )}
    />
  )
}

function Row({ label, value, currency, strong = false }: { label: string; value: string | number; currency: string; strong?: boolean }) {
  return (
    <div className={cn('flex items-baseline justify-between gap-4', strong && 'border-t border-border pt-3')}>
      <dt className={cn(strong ? 'font-bold text-fg' : 'text-muted')}>{label}</dt>
      <dd className={cn(strong ? 'text-2xl font-extrabold tracking-[-0.02em] text-fg' : 'text-fg')}>
        <MoneyText value={value} currency={currency} />
      </dd>
    </div>
  )
}

function Summary({
  hotel,
  stay,
  quote,
  updating,
  exempt,
  paymentOption,
  bare = false,
}: {
  hotel: PropertyDetail
  stay: Stay
  quote: CheckoutQuote | undefined
  updating: boolean
  exempt: boolean
  paymentOption: PaymentOption
  /** Inside the phone's fold-out summary: no card of its own and no hotel header (already in the fold). */
  bare?: boolean
}) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const currency = hotel.currency
  const lodgingNet = quote ? quote.items.reduce((sum, item) => sum + Number(item.net), 0) : 0
  const extrasNet = quote ? quote.extras.reduce((sum, extra) => sum + Number(extra.net), 0) : 0
  const due = quote ? quote.due_now[paymentOption] : '0'
  const later = quote ? Number(quote.total) - Number(due) : 0

  return (
    <div className={cn(!bare && 'overflow-hidden rounded-2xl border border-border bg-surface shadow-sm')}>
      <div className={cn('flex gap-3 border-b border-border p-4', bare && 'hidden')}>
        <Photo src={hotel.photo ?? hotel.photos[0]?.url} className="size-16 shrink-0 rounded-lg" />
        <div className="min-w-0">
          <p className="truncate font-bold text-fg">{hotel.name}</p>
          <p className="text-sm text-muted">{hotel.city}</p>
          <p className="num mt-1 text-sm text-fg">
            {formatDateRange(stay.checkin, stay.checkout, lang)} · {t('common:date.nights', { count: quote?.nights ?? 0 })}
          </p>
          <p className="text-sm text-muted">{guestsLabel(stay.adults, stay.children, t)}</p>
        </div>
      </div>
      <div className={cn('p-4 transition-opacity', updating && 'opacity-60')} aria-busy={updating}>
        {!quote ? (
          <LoadingState label={t('checkout.summary.updating')} className="py-6" />
        ) : (
          <>
            <ul className="grid gap-3">
              {quote.items.map((item) => (
                <li key={`${item.room_type_id}:${item.rate_plan_id}`} className="text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="font-semibold text-fg">
                      {item.room_type_kind === 'dorm'
                        ? t('checkout.summary.beds', { count: item.units })
                        : t('checkout.summary.units', { count: item.quantity })}{' '}
                      · {tr(item.room_type_name, lang)}
                    </span>
                    <MoneyText value={item.total} currency={currency} />
                  </div>
                  <p className="text-xs text-muted">
                    {tr(item.rate_plan_name, lang)} · {t(`meal.${item.meal_plan}`)}
                  </p>
                  <PolicyLine policy={item.cancellation_policy} className="mt-1.5 text-xs" />
                </li>
              ))}
              {quote.extras.map((extra) => (
                <li key={extra.extra_id} className="flex justify-between gap-3 text-sm">
                  <span className="text-fg">
                    {tr(extra.name, lang)} <span className="text-muted">× {extra.quantity}</span>
                  </span>
                  <MoneyText value={extra.total} currency={currency} />
                </li>
              ))}
            </ul>
            <dl className="mt-4 grid gap-2 border-t border-border pt-4 text-sm">
              <Row label={t('checkout.summary.lodging')} value={lodgingNet} currency={currency} />
              {extrasNet > 0 && <Row label={t('checkout.extras.title')} value={extrasNet} currency={currency} />}
              <Row label={t('checkout.summary.tax')} value={quote.tax_total} currency={currency} />
              {exempt && <p className="-mt-1 text-right text-xs font-semibold text-success-ink">{t('checkout.summary.taxExempt')}</p>}
              {Number(quote.discount_total) > 0 && (
                <p className="text-right text-xs text-muted">
                  {t('checkout.summary.discount')}: {moneyLabel(quote.discount_total, currency)}
                </p>
              )}
              <Row label={t('checkout.summary.total')} value={quote.total} currency={currency} strong />
              <Row label={t('checkout.summary.dueNow')} value={due} currency={currency} />
              {later > 0 && <Row label={t('checkout.summary.dueLater')} value={later} currency={currency} />}
            </dl>
          </>
        )}
      </div>
    </div>
  )
}
