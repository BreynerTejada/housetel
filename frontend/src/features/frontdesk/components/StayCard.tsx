import { BedDouble, CalendarRange, ChevronDown, LogIn, LogOut } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import type { ReservationDetail, StayDetail } from '../api'
import { stayLine, tr, unitLabel } from '../lib/labels'
import { stayActions, type StayAction } from '../lib/stays'

/** One room of the reservation: key tag, category and rate, dates, nights and its actions. */
export function StayCard({
  reservation,
  stay,
  onAction,
}: {
  reservation: ReservationDetail
  stay: StayDetail
  onAction: (stay: StayDetail, action: StayAction) => void
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const nightsId = useId()
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? stay.checkin_date
  const canCheck = useCan('bookings.checkin')
  const canManage = useCan('bookings.manage')
  const [showNights, setShowNights] = useState(false)
  const unit = unitLabel(stay.room?.number, stay.bed?.label)
  const actions = stayActions(stay, bd).filter((action) => (action === 'checkin' || action === 'checkout' ? canCheck : canManage))
  const inactive = stay.status === 'cancelled' || stay.status === 'no_show'

  return (
    <article aria-labelledby={titleId} className="rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex items-start gap-4">
        {unit ? (
          <RoomKeyTag number={unit} status={stay.status === 'checked_in' ? 'occupied' : (stay.room?.housekeeping_status ?? 'clean')} size="lg" inactive={inactive} />
        ) : (
          <span className="inline-flex h-14 min-w-18 flex-col items-center justify-center rounded-md border border-dashed border-border-strong px-2 text-center text-[11px] font-semibold text-muted">
            <BedDouble aria-hidden className="mb-0.5 size-4" />
            {t('stay.noRoom')}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={titleId} className="text-[15px] font-bold">
              {tr(stay.room_type.name, i18n.language)}
            </h3>
            {stay.status !== reservation.status && <StatusBadge kind="reservation" status={stay.status} />}
          </div>
          <p className="text-[13px] text-fg">{tr(stay.rate_plan.name, i18n.language)}</p>
          <p className="text-[13px] text-muted">
            {t(`mealPlans.${stay.rate_plan.meal_plan}`, { defaultValue: stay.rate_plan.meal_plan })}
          </p>
          <p className="num mt-1 text-[13px] text-muted">
            {stayLine(t, lang, { checkin: stay.checkin_date, checkout: stay.checkout_date, nights: stay.nights, adults: stay.adults, children: stay.children })}
          </p>
          {(stay.checked_in_at || stay.checked_out_at) && (
            <p className="num text-xs text-muted">
              {stay.checked_in_at && t('stay.checkedInAt', { date: formatDate(stay.checked_in_at, lang === 'en' ? 'MMM d, HH:mm' : 'd MMM, HH:mm', lang) })}
              {stay.checked_out_at && ` · ${t('stay.checkedOutAt', { date: formatDate(stay.checked_out_at, lang === 'en' ? 'MMM d, HH:mm' : 'd MMM, HH:mm', lang) })}`}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <MoneyText value={stay.total_amount} currency={reservation.currency} className="block text-[15px] font-bold text-fg" />
          <button
            type="button"
            onClick={() => setShowNights((value) => !value)}
            aria-expanded={showNights}
            aria-controls={nightsId}
            className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-fg"
          >
            {t('stay.nights')}
            <ChevronDown aria-hidden className={showNights ? 'size-3.5 rotate-180' : 'size-3.5'} />
          </button>
        </div>
      </div>

      {showNights && (
        <ul id={nightsId} className="mt-3 grid gap-1 border-t border-border pt-3 text-[13px] sm:grid-cols-2">
          {stay.nightly_rates.map((night) => (
            <li key={night.date} className="flex justify-between gap-3">
              <span className="text-muted">{formatDate(night.date, lang === 'en' ? 'EEE, MMM d' : 'EEE d MMM', lang)}</span>
              <MoneyText value={night.amount} currency={reservation.currency} />
            </li>
          ))}
        </ul>
      )}

      {actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3">
          {actions.includes('checkin') && (
            <Button size="sm" variant={reservation.flags.ready_for_checkin ? 'primary' : 'secondary'} onClick={() => onAction(stay, 'checkin')}>
              <LogIn aria-hidden />
              {t('actions.checkIn')}
            </Button>
          )}
          {actions.includes('checkout') && (
            <Button size="sm" variant="primary" onClick={() => onAction(stay, 'checkout')}>
              <LogOut aria-hidden />
              {t('actions.checkOut')}
            </Button>
          )}
          {actions.includes('assign') && (
            <Button size="sm" onClick={() => onAction(stay, 'assign')}>
              <BedDouble aria-hidden />
              {stay.room ? t('assign.titleMove') : t('assign.title')}
            </Button>
          )}
          {actions.includes('modify') && (
            <Button size="sm" onClick={() => onAction(stay, 'modify')}>
              <CalendarRange aria-hidden />
              {t('modify.title')}
            </Button>
          )}
        </div>
      )}
    </article>
  )
}
