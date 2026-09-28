import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { LegalFooterLinks } from '@/features/saas/components/LegalFooterLinks'
import { isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { usePortal, type PortalSummary } from '../api'
import { BalanceCard } from '../components/portal/BalanceCard'
import { HotelInfo, InvoicesSection } from '../components/portal/InfoSections'
import { InvalidLink } from '../components/portal/InvalidLink'
import { KeyCard } from '../components/portal/KeyCard'
import { ManageSection } from '../components/portal/ManageSection'
import { MessagesSection } from '../components/portal/MessagesSection'
import { PaymentReturnBanner } from '../components/portal/PaymentReturnBanner'
import { HotelMark, LanguageToggle, PortalFrame } from '../components/portal/PortalFrame'
import { ExtrasSection, RequestsSection } from '../components/portal/ServicesSection'
import { useReservationLanguage } from '../lib/language'
import { daysUntil, firstWord } from '../lib/text'

/**
 * `/g/:token` — the guest's own page for the booking (magic link from the confirmation and pre-arrival
 * messages): the registration card with the online check-in, the account, extras and requests, invoices,
 * changes within the policy and how to reach the hotel. Mobile first, in the hotel's colors. The chat
 * bubble is mounted by the public layout (`PublicChatSlot` receives the token).
 */
export default function PortalPage() {
  const { token = '' } = useParams()
  const portal = usePortal(token)
  useReservationLanguage(portal.data?.reservation.code, portal.data?.reservation.language)

  if (portal.isPending) return <PortalSkeleton />
  if (portal.isError) {
    return isApiError(portal.error) && portal.error.status === 404 ? (
      <InvalidLink />
    ) : (
      <PortalFrame className="items-center justify-center px-4">
        <ErrorState error={portal.error} onRetry={() => portal.refetch()} />
      </PortalFrame>
    )
  }
  return <PortalView summary={portal.data} token={token} />
}

function PortalView({ summary, token }: { summary: PortalSummary; token: string }) {
  const { t } = useTranslation('guestportal')
  const checkinPending = summary.checkin.is_open && summary.checkin.status !== 'completed'

  return (
    <PortalFrame property={summary.property}>
      <Hero summary={summary} />
      <div className="relative z-10 mx-auto -mt-14 grid w-full max-w-xl gap-7 px-4 pb-14 sm:px-6">
        <PaymentReturnBanner token={token} />
        <KeyCard summary={summary} token={token} primary={checkinPending} />
        <BalanceCard balance={summary.balance} payments={summary.payments} token={token} primary={!checkinPending} />
        <ExtrasSection summary={summary} token={token} />
        <RequestsSection summary={summary} token={token} />
        <MessagesSection messages={summary.messages ?? []} property={summary.property} />
        <InvoicesSection token={token} />
        <ManageSection summary={summary} token={token} />
        <HotelInfo property={summary.property} />
        <footer className="grid justify-items-center gap-1.5 pt-2 text-center">
          <p className="text-xs text-subtle">{t('footer')}</p>
          <LegalFooterLinks />
        </footer>
      </div>
    </PortalFrame>
  )
}

/** The hotel's photo (or a quiet band) with the greeting: who, where and how long until the stay. */
function Hero({ summary }: { summary: PortalSummary }) {
  const { t } = useTranslation('guestportal')
  const { property } = summary
  const photo = property.photo
  const booker = summary.guests.find((guest) => guest.role === 'booker')
  const name = booker?.first_name || firstWord(booker?.full_name ?? '')

  return (
    <header className={cn('relative isolate overflow-hidden', photo ? 'text-white' : 'hatch border-b border-border bg-surface-2 text-fg')}>
      {photo && (
        <>
          <img src={photo} alt="" className="absolute inset-0 -z-20 size-full object-cover" />
          <div aria-hidden className="absolute inset-0 -z-10 bg-gradient-to-b from-black/55 via-black/35 to-black/70" />
        </>
      )}
      <div className="mx-auto w-full max-w-xl px-4 pt-4 pb-24 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <HotelMark property={property} size="sm" />
            <p className="truncate text-[15px] font-bold tracking-[-0.01em]">{property.name}</p>
          </div>
          <LanguageToggle tone={photo ? 'overlay' : 'surface'} />
        </div>
        <h1 className="mt-9 text-[32px] leading-9 font-extrabold tracking-[-0.035em] sm:text-[38px] sm:leading-[2.6rem]">
          {name ? t('greeting', { name }) : t('greetingAnonymous')}
        </h1>
        <p className={cn('mt-1.5 text-[15px]', photo ? 'text-white/90' : 'text-muted')}>{whenLine(summary, t)}</p>
      </div>
    </header>
  )
}

function whenLine(summary: PortalSummary, t: (key: string, options?: Record<string, unknown>) => string): string {
  const { reservation, today, property } = summary
  if (reservation.status === 'cancelled') return t('when.cancelled')
  if (reservation.status === 'no_show') return t('when.noShow')
  if (reservation.status === 'checked_out' || today >= reservation.checkout_date) return t('when.past', { hotel: property.name })
  if (reservation.status === 'checked_in') return t('when.inHouse', { hotel: property.name })
  if (reservation.status === 'tentative') return t('when.tentative')
  const days = daysUntil(reservation.checkin_date, today)
  if (days <= 0) return t('when.today', { city: property.city })
  if (days === 1) return t('when.tomorrow', { city: property.city })
  return t('when.days', { count: days, city: property.city })
}

function PortalSkeleton() {
  const { t } = useTranslation('guestportal')
  return (
    <PortalFrame>
      <div role="status" aria-label={t('loading')} className="contents">
        <div className="h-52 bg-surface-2" />
        <div className="mx-auto -mt-14 grid w-full max-w-xl gap-6 px-4 sm:px-6">
          <Skeleton className="h-80 rounded-2xl bg-surface-3" />
          <Skeleton className="h-36 rounded-2xl" />
        </div>
      </div>
    </PortalFrame>
  )
}
