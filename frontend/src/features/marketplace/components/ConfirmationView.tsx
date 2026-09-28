import { CalendarPlus, CircleCheck, CircleX, Clock3, ExternalLink, Hourglass, LoaderCircle, Mail, Phone } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { paymentReturnParams, usePaymentStatus } from '@/features/finance/api'
import { isApiError } from '@/lib/api'
import { formatDate, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useBookingStatus, type BookingStatus, type LinkStatus, type Via } from '../api'
import { buildIcs, downloadIcs } from '../lib/ics'
import { hotelHref } from '../lib/links'
import { goToPayment } from '../lib/navigation'
import { recallBookingEmail, rememberBookingEmail } from '../lib/storage'
import { guestsLabel, tr } from '../lib/text'
import { PolicyLine } from './RoomTypeCard'

type State = 'confirmed' | 'pending' | 'unpaid' | 'declined' | 'expired' | 'cancelled'

const LONG_DATE: Record<Lang, string> = { es: "EEEE d 'de' MMMM", en: 'EEEE, MMMM d' }
const CARD_DATE: Record<Lang, string> = { es: 'EEE d MMM yyyy', en: 'EEE, MMM d, yyyy' }

/** What the guest should understand first, from the booking and the latest word of the payment gateway. */
function confirmationState(booking: BookingStatus, link: LinkStatus | undefined, returnedFromGateway: boolean): State {
  if (booking.status === 'cancelled' || booking.status === 'no_show') return link === 'expired' ? 'expired' : 'cancelled'
  if (booking.status !== 'tentative') return 'confirmed'
  if (link === 'approved') return 'pending' // the payment is in; the confirmation follows in a moment
  if (link === 'declined' || link === 'error') return 'declined'
  if (link === 'expired') return 'expired'
  return returnedFromGateway ? 'pending' : 'unpaid'
}

const HEAD: Record<State, { icon: LucideIcon; tone: string }> = {
  confirmed: { icon: CircleCheck, tone: 'bg-success-soft text-success-ink' },
  pending: { icon: LoaderCircle, tone: 'bg-info-soft text-info-ink' },
  unpaid: { icon: Hourglass, tone: 'bg-warning-soft text-warning-ink' },
  declined: { icon: CircleX, tone: 'bg-danger-soft text-danger-ink' },
  expired: { icon: Clock3, tone: 'bg-stone-soft text-stone-ink' },
  cancelled: { icon: CircleX, tone: 'bg-stone-soft text-stone-ink' },
}

function timeIn(iso: string | null, timeZone: string, lang: Lang): string {
  if (!iso) return ''
  try {
    return new Intl.DateTimeFormat(lang === 'en' ? 'en-US' : 'es-CO', { hour: '2-digit', minute: '2-digit', timeZone }).format(new Date(iso))
  } catch {
    return ''
  }
}

function EmailForm({ code, error, onSubmit }: { code: string; error: boolean; onSubmit: (email: string) => void }) {
  const { t } = useTranslation('marketplace')
  const [value, setValue] = useState('')
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (value.trim()) onSubmit(value.trim().toLowerCase())
  }
  return (
    <form onSubmit={submit} className="mx-auto mt-10 max-w-md rounded-2xl border border-border bg-surface p-6 shadow-sm">
      <h1 className="text-2xl font-extrabold tracking-[-0.03em] text-fg">{t('confirmation.emailTitle')}</h1>
      <p className="mt-2 text-sm text-muted">{t('confirmation.emailBody', { code })}</p>
      <div className="mt-5 grid gap-1.5">
        <Label htmlFor="booking-email">{t('confirmation.email')}</Label>
        <Input id="booking-email" type="email" autoComplete="email" value={value} onChange={(event) => setValue(event.target.value)} aria-invalid={error} />
        {error && (
          <p role="alert" className="text-xs font-medium text-danger-ink">
            {t('confirmation.notFound')}
          </p>
        )}
      </div>
      <Button type="submit" variant="primary" className="mt-5 w-full">
        {t('confirmation.open')}
      </Button>
    </form>
  )
}

/**
 * Where the guest lands after booking (and after the payment gateway): the state of the booking in plain words,
 * the code as a key tag, the stay, what was paid and what is left, and the way to the guest portal.
 */
export function ConfirmationView({ code, via }: { code: string; via: Via }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const location = useLocation()
  const stateEmail = (location.state as { email?: string } | null)?.email ?? null
  const [email, setEmail] = useState<string | null>(() => stateEmail ?? recallBookingEmail(code))
  const { reference, transactionId } = paymentReturnParams(location.search)
  const payment = usePaymentStatus(reference, { transactionId })
  const booking = useBookingStatus(code, email)
  const { refetch } = booking
  const approved = payment.data?.status === 'approved'

  // The approved payment confirms the reservation on the server: read it again.
  useEffect(() => {
    if (approved) void refetch()
  }, [approved, refetch])

  const notFound = isApiError(booking.error) && booking.error.status === 404
  if (!email || notFound) {
    return (
      <div className="px-4 pb-16">
        <EmailForm
          code={code}
          error={notFound}
          onSubmit={(value) => {
            rememberBookingEmail(code, value)
            setEmail(value)
          }}
        />
      </div>
    )
  }
  if (booking.isPending) return <LoadingState className="min-h-[50vh]" />
  if (booking.isError) return <ErrorState error={booking.error} onRetry={() => void refetch()} className="min-h-[50vh] justify-center" />

  const data = booking.data
  const link = payment.data?.status ?? data.payment?.status
  const state = confirmationState(data, link, Boolean(reference))
  const { icon: Icon, tone } = HEAD[state]
  const payUrl = data.payment?.checkout_url ?? null
  const hotelLink = hotelHref(data.property.slug, null, via)
  const holdTime = timeIn(data.hold_expires_at, data.property.timezone, lang)

  const titles: Record<State, string> = {
    confirmed: t('confirmation.confirmedTitle'),
    pending: t('confirmation.pendingTitle'),
    unpaid: t('confirmation.unpaidTitle'),
    declined: t('confirmation.declinedTitle'),
    expired: t('confirmation.expiredTitle'),
    cancelled: t('confirmation.cancelledTitle'),
  }
  const bodies: Record<State, string> = {
    confirmed: t('confirmation.confirmedBody', { hotel: data.property.name, date: formatDate(data.checkin, LONG_DATE[lang], lang) }),
    pending: t('confirmation.pendingBody'),
    unpaid: holdTime ? t('confirmation.unpaidBody', { time: holdTime }) : '',
    declined: t('confirmation.declinedBody'),
    expired: t('confirmation.expiredBody'),
    cancelled: '',
  }

  function addToCalendar() {
    const content = buildIcs({
      code: data.code,
      hotelName: data.property.name,
      address: [data.property.address, data.property.city].filter(Boolean).join(', '),
      checkin: data.checkin,
      checkout: data.checkout,
      description: t('confirmation.icsDescription', {
        code: data.code,
        checkin: data.property.check_in_time ?? '',
        checkout: data.property.check_out_time ?? '',
      }),
      url: data.portal_url,
    })
    downloadIcs(`${data.code}.ics`, content)
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pt-10 pb-20 sm:px-6 sm:pt-14">
      <header className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
        <span className={cn('grid size-12 shrink-0 place-items-center rounded-full', tone)}>
          <Icon aria-hidden className={cn('size-6', state === 'pending' && 'animate-spin')} />
        </span>
        <div>
          <h1 className="text-3xl leading-tight font-extrabold tracking-[-0.035em] text-fg sm:text-4xl">{titles[state]}</h1>
          {bodies[state] && <p className="mt-1 text-muted">{bodies[state]}</p>}
        </div>
      </header>

      {(state === 'unpaid' || state === 'declined') && payUrl && (
        <Button variant="primary" size="lg" className="mt-6" onClick={() => goToPayment(payUrl)}>
          {state === 'declined' ? t('confirmation.retry') : t('confirmation.pay')}
        </Button>
      )}
      {state === 'expired' && (
        <Button asChild variant="primary" size="lg" className="mt-6">
          <Link to={hotelLink}>{t('confirmation.bookAgain')}</Link>
        </Button>
      )}

      <div className="mt-10 grid gap-6 md:grid-cols-[17rem_minmax(0,1fr)]">
        {/* the code as a key tag: the guest's key to this booking */}
        <div className="relative self-start overflow-hidden rounded-2xl bg-accent px-6 pt-10 pb-6 text-on-accent shadow-md">
          <span aria-hidden className="absolute top-4 right-5 size-4 rounded-full bg-bg" />
          <p className="text-xs font-bold tracking-[0.08em] uppercase opacity-80">{t('confirmation.code')}</p>
          <p className="num mt-1 text-[2rem] leading-none font-extrabold tracking-[0.02em]">{data.code}</p>
          <p className="mt-4 text-sm leading-snug opacity-90">{data.property.name}</p>
          <p className="mt-5 border-t border-current/25 pt-3 text-xs leading-relaxed opacity-85">{t('confirmation.keepCode')}</p>
        </div>

        <div className="grid gap-6">
          <div className="grid grid-cols-2 gap-4 rounded-2xl border border-border bg-surface p-5">
            <div>
              <p className="eyebrow">{t('confirmation.checkin')}</p>
              <p className="mt-1 font-bold text-fg">{formatDate(data.checkin, CARD_DATE[lang], lang)}</p>
              {data.property.check_in_time && <p className="text-sm text-muted">{t('confirmation.from', { time: data.property.check_in_time })}</p>}
            </div>
            <div>
              <p className="eyebrow">{t('confirmation.checkout')}</p>
              <p className="mt-1 font-bold text-fg">{formatDate(data.checkout, CARD_DATE[lang], lang)}</p>
              {data.property.check_out_time && <p className="text-sm text-muted">{t('confirmation.until', { time: data.property.check_out_time })}</p>}
            </div>
            <div className="col-span-2 border-t border-border pt-4">
              <p className="eyebrow">{t('confirmation.stay')}</p>
              <p className="mt-1 text-fg">
                {t('common:date.nights', { count: data.nights })} · {guestsLabel(data.adults, data.children, t)}
              </p>
              <ul className="mt-2 grid gap-1 text-sm">
                {data.rooms.map((room, index) => (
                  <li key={index} className="flex justify-between gap-3">
                    <span className="text-fg">
                      {room.units} × {tr(room.room_type_name, lang)}
                      <span className="text-muted">
                        {' '}
                        · {tr(room.rate_plan_name, lang)} · {t(`meal.${room.meal_plan}`)}
                      </span>
                    </span>
                    <MoneyText value={room.total} currency={data.currency} />
                  </li>
                ))}
                {data.extras.map((extra, index) => (
                  <li key={`extra-${index}`} className="flex justify-between gap-3">
                    <span className="text-fg">
                      {extra.description} <span className="text-muted">× {extra.quantity}</span>
                    </span>
                    <MoneyText value={extra.total} currency={data.currency} />
                  </li>
                ))}
              </ul>
            </div>
            <dl className="col-span-2 grid gap-1.5 border-t border-border pt-4 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="font-bold text-fg">{t('confirmation.total')}</dt>
                <dd className="text-lg font-extrabold text-fg">
                  <MoneyText value={data.total} currency={data.currency} />
                </dd>
              </div>
              {Number(data.paid) > 0 && (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{t('confirmation.paid')}</dt>
                  <dd>
                    <MoneyText value={data.paid} currency={data.currency} />
                  </dd>
                </div>
              )}
              {Number(data.balance) > 0 && (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{t('confirmation.balance')}</dt>
                  <dd>
                    <MoneyText value={data.balance} currency={data.currency} />
                  </dd>
                </div>
              )}
              {data.tax_exempt && <p className="text-right text-xs font-semibold text-success-ink">{t('confirmation.taxExempt')}</p>}
            </dl>
            {data.cancellation_policy && (
              <div className="col-span-2 border-t border-border pt-4">
                <p className="eyebrow">{t('confirmation.cancellation')}</p>
                <PolicyLine policy={data.cancellation_policy} className="mt-1.5" />
              </div>
            )}
            {(data.special_requests || data.eta) && (
              <div className="col-span-2 border-t border-border pt-4 text-sm">
                <p className="eyebrow">{t('confirmation.requests')}</p>
                {data.eta && <p className="mt-1 text-fg">{t('confirmation.eta', { time: data.eta })}</p>}
                {data.special_requests && <p className="mt-1 whitespace-pre-line text-muted">{data.special_requests}</p>}
              </div>
            )}
          </div>

          {state !== 'expired' && state !== 'cancelled' && (
            <div className="grid gap-4 rounded-2xl border border-border bg-surface-2/60 p-5">
              <div className="flex flex-wrap gap-2">
                <Button asChild variant={state === 'confirmed' ? 'primary' : 'secondary'}>
                  <a href={data.portal_url}>
                    {t('confirmation.portal')}
                    <ExternalLink aria-hidden />
                  </a>
                </Button>
                <Button onClick={addToCalendar}>
                  <CalendarPlus aria-hidden />
                  {t('confirmation.calendar')}
                </Button>
                <Button asChild variant="ghost">
                  <Link to={hotelLink}>{t('confirmation.hotel')}</Link>
                </Button>
              </div>
              <p className="text-sm text-muted">{t('confirmation.portalHint')}</p>
            </div>
          )}

          {(data.property.phone || data.property.email) && (
            <div className="text-sm">
              <p className="font-semibold text-fg">{t('confirmation.contact')}</p>
              <ul className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
                {data.property.phone && (
                  <li>
                    <a href={`tel:${data.property.phone.replace(/\s+/g, '')}`} className="inline-flex items-center gap-1.5 text-fg hover:underline">
                      <Phone aria-hidden className="size-4 text-muted" />
                      {data.property.phone}
                    </a>
                  </li>
                )}
                {data.property.email && (
                  <li>
                    <a href={`mailto:${data.property.email}`} className="inline-flex items-center gap-1.5 text-fg hover:underline">
                      <Mail aria-hidden className="size-4 text-muted" />
                      {data.property.email}
                    </a>
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
