import { ArrowUpRight, Mail, Phone } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { GuestAvatar } from '@/features/guests/components/GuestAvatar'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import type { ConversationDetail } from '../api'

function countryName(code: string, lang: string): string {
  if (!code) return ''
  try {
    return new Intl.DisplayNames([lang], { type: 'region' }).of(code) ?? code
  } catch {
    return code
  }
}

/**
 * Who the guest is and what they booked, beside the thread: the answer to most questions is here
 * (dates, room, balance) without leaving the inbox.
 */
export function ContextPanel({ conversation }: { conversation: ConversationDetail }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const canSeeBookings = useCan('bookings.view')
  const canSeeGuests = useCan('guests.view')
  const { guest, reservation } = conversation.context
  const owes = reservation ? Number(reservation.balance) > 0 : false

  return (
    <div className="grid gap-6 p-5">
      <section aria-labelledby="context-reservation" className="grid gap-3">
        <h3 id="context-reservation" className="eyebrow">
          {t('context.reservation')}
        </h3>
        {reservation ? (
          <div className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="num text-[15px] font-bold tracking-tight">{reservation.code}</span>
              <StatusBadge kind="reservation" status={reservation.status} />
            </div>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px]">
              <dt className="text-muted">{t('context.stay')}</dt>
              <dd className="text-right">
                <span className="num">{formatDateRange(reservation.checkin_date, reservation.checkout_date, lang)}</span>
                <span className="block text-muted">{t('context.nights', { count: reservation.nights })}</span>
              </dd>
              <dt className="text-muted">{t('context.guests')}</dt>
              <dd className="text-right">
                {t('context.adults', { count: reservation.adults })}
                {reservation.children > 0 && `, ${t('context.children', { count: reservation.children })}`}
              </dd>
              <dt className="text-muted">{t('context.rooms')}</dt>
              <dd className="flex flex-wrap items-center justify-end gap-1.5">
                {reservation.rooms.length ? (
                  reservation.rooms.map((room) => <RoomKeyTag key={room} number={room} status="occupied" size="sm" />)
                ) : (
                  <span className="text-muted">{t('context.unassignedRoom')}</span>
                )}
                {reservation.room_types.length > 0 && (
                  <span className="basis-full text-right text-muted">{reservation.room_types.join(', ')}</span>
                )}
              </dd>
              <dt className="text-muted">{t('context.total')}</dt>
              <dd className="text-right">
                <MoneyText value={reservation.total_amount} currency={reservation.currency} />
              </dd>
              <dt className="text-muted">{t('context.balance')}</dt>
              <dd className="text-right">
                {owes ? (
                  <MoneyText value={reservation.balance} currency={reservation.currency} className="font-bold text-warning-ink" />
                ) : (
                  <Badge tone="success">{t('context.paid')}</Badge>
                )}
              </dd>
            </dl>
            {canSeeBookings && (
              <Link
                to={`/app/reservations/${reservation.id}`}
                className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline"
              >
                {t('context.openReservation')}
                <ArrowUpRight aria-hidden className="size-3.5" />
              </Link>
            )}
          </div>
        ) : (
          <p className="text-[13px] text-muted">{t('context.noReservation')}</p>
        )}
      </section>

      <section aria-labelledby="context-guest" className="grid gap-3">
        <h3 id="context-guest" className="eyebrow">
          {guest ? t('context.guest') : t('context.contact')}
        </h3>
        <div className="flex items-start gap-3">
          <GuestAvatar name={guest?.full_name ?? conversation.display_name} vip={guest?.is_vip} />
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 font-semibold">
              <span className="truncate">{guest?.full_name ?? conversation.display_name}</span>
              {guest?.is_vip && <Badge tone="accent">{t('context.vip')}</Badge>}
            </p>
            {guest?.nationality && (
              <p className="text-[13px] text-muted">
                {t('context.nationality')}: {countryName(guest.nationality, lang)}
              </p>
            )}
          </div>
        </div>
        <dl className="grid gap-2 text-[13px]">
          {(guest?.email || conversation.channel === 'email') && (
            <div className="flex items-center gap-2">
              <dt>
                <Mail aria-hidden className="size-3.5 text-muted" />
                <span className="sr-only">{t('context.email')}</span>
              </dt>
              <dd className="min-w-0 truncate">{guest?.email || conversation.address}</dd>
            </div>
          )}
          {(guest?.phone || conversation.channel === 'whatsapp') && (
            <div className="flex items-center gap-2">
              <dt>
                <Phone aria-hidden className="size-3.5 text-muted" />
                <span className="sr-only">{t('context.phone')}</span>
              </dt>
              <dd className="num">{guest?.phone || conversation.address}</dd>
            </div>
          )}
          {guest?.language && (
            <div className="flex items-center gap-2">
              <dt className="text-muted">{t('context.language')}:</dt>
              <dd>{t(`languages.${guest.language === 'en' ? 'en' : 'es'}`)}</dd>
            </div>
          )}
        </dl>
        {guest && canSeeGuests && (
          <Link
            to={`/app/guests/${guest.id}`}
            className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline"
          >
            {t('context.openGuest')}
            <ArrowUpRight aria-hidden className="size-3.5" />
          </Link>
        )}
      </section>
    </div>
  )
}
