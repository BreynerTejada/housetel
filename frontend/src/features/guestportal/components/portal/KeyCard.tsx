import { ArrowRight, CalendarClock, Check, KeyRound } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatDate, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { PortalSummary } from '../../api'
import { tr } from '../../lib/text'

/**
 * The booking as a hotel registration card: the hotel's color band with the code, the two dates set large
 * like the numbers on a key tag, and — past a perforated tear line — the stub with what is left to do
 * before arrival (the online check-in). It is the one element the portal is remembered by.
 */
export function KeyCard({ summary, token, primary }: { summary: PortalSummary; token: string; primary: boolean }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const { reservation, property, stays } = summary
  const people = [
    t('card.adults', { count: reservation.adults }),
    reservation.children ? t('card.children', { count: reservation.children }) : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <article
      aria-labelledby="key-card-code"
      className={cn(
        'relative overflow-hidden rounded-2xl border border-border bg-surface shadow-md',
        reservation.status === 'cancelled' && 'opacity-90',
      )}
    >
      <header className="flex items-center justify-between gap-3 bg-accent px-5 py-3 text-on-accent">
        <span className="text-[11px] font-bold tracking-[0.12em] uppercase opacity-85">{t('card.reservation')}</span>
        <span id="key-card-code" className="num text-[15px] font-extrabold tracking-[0.16em]">
          {reservation.code}
        </span>
      </header>

      <div className="grid grid-cols-2 gap-4 px-5 pt-5 pb-4">
        <DateBlock label={t('card.arrival')} date={reservation.checkin_date} lang={lang}>
          {property.check_in_time && t('card.from', { time: property.check_in_time })}
        </DateBlock>
        <DateBlock label={t('card.departure')} date={reservation.checkout_date} lang={lang} align="end">
          {property.check_out_time && t('card.until', { time: property.check_out_time })}
        </DateBlock>
      </div>

      <div className="grid gap-1 px-5 pb-5 text-sm">
        <p className="font-semibold">
          {t('card.nights', { count: reservation.nights })} · {people}
        </p>
        {stays.map((stay) => (
          <p key={stay.id} className="text-muted">
            {tr(stay.room_type.name, lang)}
            {' · '}
            {tr(stay.rate_plan.name, lang)}
            {stay.rate_plan.meal_plan !== 'room_only' && ` · ${t(`card.mealPlans.${stay.rate_plan.meal_plan}`, { defaultValue: '' })}`}
            {stay.room && (
              <span className="ml-1.5 inline-flex items-center gap-1 font-semibold text-fg">
                <KeyRound aria-hidden className="size-3.5" />
                {t('card.room', { number: stay.room.number })}
              </span>
            )}
          </p>
        ))}
      </div>

      <Perforation />

      <CheckinStub summary={summary} token={token} primary={primary} lang={lang} />
    </article>
  )
}

function DateBlock({
  label,
  date,
  lang,
  align = 'start',
  children,
}: {
  label: string
  date: string
  lang: Lang
  align?: 'start' | 'end'
  children?: ReactNode
}) {
  return (
    <div className={cn('min-w-0', align === 'end' && 'text-right')}>
      <p className="eyebrow">{label}</p>
      <p className={cn('mt-1 flex items-baseline gap-1.5', align === 'end' && 'justify-end')}>
        <span className="num text-[44px] leading-none font-bold tracking-[-0.045em]">{formatDate(date, 'd', lang)}</span>
        <span className="text-[15px] font-bold tracking-[0.04em] uppercase">{formatDate(date, 'MMM', lang).replace('.', '')}</span>
      </p>
      <p className="mt-1.5 text-[13px] text-muted first-letter:uppercase">
        {formatDate(date, 'EEEE', lang)}
        {children ? <span className="block">{children}</span> : null}
      </p>
    </div>
  )
}

/** The tear line: a dashed rule between two punched notches. */
function Perforation() {
  return (
    <div aria-hidden className="relative h-5">
      <span className="absolute top-1/2 -left-2.5 size-5 -translate-y-1/2 rounded-full border border-border bg-bg" />
      <span className="absolute top-1/2 -right-2.5 size-5 -translate-y-1/2 rounded-full border border-border bg-bg" />
      <span className="absolute inset-x-5 top-1/2 border-t-2 border-dashed border-border-strong/70" />
    </div>
  )
}

function CheckinStub({ summary, token, primary, lang }: { summary: PortalSummary; token: string; primary: boolean; lang: Lang }) {
  const { t } = useTranslation('guestportal')
  const { checkin, reservation } = summary
  const checkinPath = `/g/${encodeURIComponent(token)}/checkin`

  if (reservation.status === 'cancelled') {
    return (
      <footer className="px-5 pt-3 pb-5 text-sm text-muted">
        {t('stub.cancelled', { date: formatDate(reservation.cancelled_at, undefined, lang) })}
      </footer>
    )
  }
  if (checkin.status === 'completed') {
    return (
      <footer className="flex items-center gap-3 px-5 pt-3 pb-5">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-success-soft text-success-ink motion-safe:animate-pop-in">
          <Check aria-hidden className="size-5" strokeWidth={2.5} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{t('stub.done')}</p>
          <p className="text-sm text-muted">{reservation.eta ? t('stub.doneEta', { eta: reservation.eta }) : t('stub.doneHint')}</p>
        </div>
        <Link to={checkinPath} className="shrink-0 text-sm font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('stub.view')}
        </Link>
      </footer>
    )
  }
  if (checkin.is_open) {
    const started = checkin.status === 'in_progress'
    return (
      <footer className="grid gap-3 px-5 pt-3 pb-5 sm:flex sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="font-bold">{started ? t('stub.inProgress') : t('stub.open')}</p>
          <p className="text-sm text-muted">
            {started ? t('stub.inProgressHint', { step: t(`checkin.steps.${checkin.current_step}`) }) : t('stub.openHint')}
          </p>
        </div>
        <Button asChild variant={primary ? 'primary' : 'secondary'} size="lg" className="w-full sm:w-auto">
          <Link to={checkinPath}>
            {started ? t('stub.continue') : t('stub.start')}
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </footer>
    )
  }
  if (checkin.reason === 'not_open_yet') {
    return (
      <footer className="flex items-center gap-3 px-5 pt-3 pb-5">
        <CalendarClock aria-hidden className="size-5 shrink-0 text-muted" />
        <p className="text-sm text-muted">{t('stub.notYet', { date: formatDate(checkin.opens_on, lang === 'en' ? 'MMMM d' : "d 'de' MMMM", lang) })}</p>
      </footer>
    )
  }
  return (
    <footer className="px-5 pt-3 pb-5 text-sm text-muted">
      {t(`stub.closed.${checkin.reason ?? 'past'}`, { defaultValue: t('stub.closed.past') })}
    </footer>
  )
}
