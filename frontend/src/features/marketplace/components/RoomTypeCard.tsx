import { Accessibility, Ban, BedDouble, CircleAlert, CircleCheck, Maximize2, Minus, Plus, UsersRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CancellationPolicy, Offer, RoomTypeInfo } from '../api'
import { quantityLeft, type SelectionItem } from '../lib/selection'
import { bedsLabel, moneyLabel, policySummary, tr } from '../lib/text'
import { AmenityChip, Photo } from './Cards'

const SCARCE = 3

export function PolicyLine({ policy, className }: { policy: CancellationPolicy | null | undefined; className?: string }) {
  const { t } = useTranslation('marketplace')
  const summary = policySummary(policy, t)
  const Icon = summary.tone === 'free' ? CircleCheck : summary.tone === 'strict' ? Ban : CircleAlert
  return (
    <p className={cn('flex items-start gap-1.5 text-sm', className)}>
      <Icon
        aria-hidden
        className={cn('mt-0.5 size-4 shrink-0', summary.tone === 'free' ? 'text-success' : summary.tone === 'strict' ? 'text-danger' : 'text-warning')}
      />
      <span>
        <span className={cn('font-semibold', summary.tone === 'free' ? 'text-success-ink' : 'text-fg')}>{summary.title}</span>
        <span className="block text-xs text-muted">{summary.detail}</span>
      </span>
    </p>
  )
}

interface RoomTypeCardProps {
  roomType: RoomTypeInfo
  /** Offers of this room type for the stay (null = no dates yet). */
  offers: Offer[] | null
  allOffers: Offer[]
  items: SelectionItem[]
  nights: number
  currency: string
  onQuantity: (offer: Offer, quantity: number) => void
}

function RoomFacts({ roomType }: { roomType: RoomTypeInfo }) {
  const { t, i18n } = useTranslation('marketplace')
  const lang = normalizeLang(i18n.language)
  const size = roomType.size_m2_range
    ? t('hotel.rooms.sizeRange', { from: formatNumber(Number(roomType.size_m2_range[0]), lang, 0), to: formatNumber(Number(roomType.size_m2_range[1]), lang, 0) })
    : roomType.size_m2
      ? t('hotel.rooms.size', { size: formatNumber(Number(roomType.size_m2), lang, 0) })
      : null
  const facts = [
    {
      icon: UsersRound,
      text: roomType.kind === 'dorm' ? t('hotel.rooms.dormBed') : t('hotel.rooms.upTo', { count: roomType.max_occupancy }),
    },
    { icon: BedDouble, text: bedsLabel(roomType.beds, t) },
    { icon: Maximize2, text: size },
    ...(roomType.accessible ? [{ icon: Accessibility, text: t('hotel.rooms.accessible') }] : []),
  ].filter((fact) => fact.text)
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
      {facts.map(({ icon: Icon, text }) => (
        <li key={text} className="flex items-center gap-1.5">
          <Icon aria-hidden className="size-4" />
          {text}
        </li>
      ))}
      {roomType.views.slice(0, 2).map((view) => (
        <li key={view}>{t(`views.${view}`, { defaultValue: view })}</li>
      ))}
    </ul>
  )
}

/** A room type with its rates for the stay: each rate has its policy, price and a quantity picker. */
export function RoomTypeCard({ roomType, offers, allOffers, items, nights, currency, onQuantity }: RoomTypeCardProps) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = i18n.language
  const name = tr(roomType.name, lang)
  const description = tr(roomType.description, lang)
  const cover = roomType.photos[0]?.url ?? offers?.[0]?.room_type.photo ?? null

  return (
    <article className="overflow-hidden rounded-2xl border border-border bg-surface shadow-xs">
      <div className="grid gap-4 p-4 sm:grid-cols-[12rem_minmax(0,1fr)] sm:p-5">
        <Photo src={cover} alt="" className="aspect-[4/3] rounded-xl" />
        <div className="min-w-0">
          <h3 className="text-lg font-bold tracking-[-0.01em] text-fg">{name}</h3>
          <RoomFacts roomType={roomType} />
          {description && <p className="mt-2 line-clamp-3 text-sm text-fg/85">{description}</p>}
          {roomType.features.length > 0 && (
            <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {roomType.features.map((feature) => (
                <div key={feature.key} className="flex gap-1">
                  <dt className="text-muted">{tr(feature.label, lang)}:</dt>
                  <dd className="font-medium text-fg">
                    {feature.display ? feature.display.map((label) => tr(label, lang)).join(', ') : String(feature.value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {roomType.amenities.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {roomType.amenities.slice(0, 6).map((amenity) => (
                <li key={amenity.code}>
                  <AmenityChip amenity={amenity} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {offers !== null && (
        <ul className="divide-y divide-border border-t border-border">
          {offers.length === 0 ? (
            <li className="px-5 py-4 text-sm text-muted">{t('hotel.rooms.unavailable')}</li>
          ) : (
            offers.map((offer) => {
              const plan = tr(offer.rate_plan.name, lang)
              const quantity = items.find((item) => item.roomTypeId === offer.room_type_id && item.ratePlanId === offer.rate_plan_id)?.quantity ?? 0
              const left = quantityLeft(offer, items, allOffers)
              const labels = { room: name, plan }
              return (
                <li key={offer.rate_plan_id} className="grid gap-4 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-5">
                  <div className="min-w-0">
                    <p className="font-bold text-fg">
                      {plan} <span className="font-medium text-muted">· {t(`meal.${offer.rate_plan.meal_plan}`)}</span>
                    </p>
                    <PolicyLine policy={offer.rate_plan.cancellation_policy} className="mt-1.5" />
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {offer.rate_plan.requires_payment && (
                        <Badge tone="info">{t('hotel.rooms.deposit', { percent: Number(offer.rate_plan.deposit_percent) })}</Badge>
                      )}
                      {offer.promo_applied && <Badge tone="accent">{t('hotel.rooms.promo', { code: offer.promo_applied })}</Badge>}
                      {offer.max_quantity <= SCARCE && <Badge tone="warning">{t('hotel.rooms.left', { count: offer.max_quantity })}</Badge>}
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-5 sm:justify-end">
                    <div className="sm:text-right">
                      <p className="text-xs text-muted">{t('hotel.rooms.totalFor', { nights: t('common:date.nights', { count: nights }) })}</p>
                      <p className="text-xl leading-tight font-extrabold tracking-[-0.02em] text-fg">
                        <MoneyText value={offer.total} currency={currency} />
                      </p>
                      <p className="text-xs text-muted">
                        {offer.units_needed > 1
                          ? t('hotel.rooms.bedsForParty', { count: offer.units_needed })
                          : t('hotel.rooms.perNight', { price: moneyLabel(offer.per_night, currency) })}
                      </p>
                    </div>
                    {quantity === 0 ? (
                      <Button
                        variant="secondary"
                        className="min-w-24"
                        aria-label={t('hotel.rooms.chooseFor', labels)}
                        disabled={left === 0}
                        onClick={() => onQuantity(offer, 1)}
                      >
                        {t('hotel.rooms.choose')}
                      </Button>
                    ) : (
                      <div role="group" aria-label={t('hotel.rooms.quantity', labels)} className="flex items-center gap-2">
                        <Button size="icon-sm" className="rounded-full" aria-label={t('hotel.rooms.decrease', labels)} onClick={() => onQuantity(offer, quantity - 1)}>
                          <Minus aria-hidden />
                        </Button>
                        <span aria-live="polite" className="num w-6 text-center text-base font-bold text-fg">
                          {quantity}
                        </span>
                        <Button
                          size="icon-sm"
                          className="rounded-full"
                          aria-label={t('hotel.rooms.increase', labels)}
                          disabled={quantity >= left}
                          onClick={() => onQuantity(offer, quantity + 1)}
                        >
                          <Plus aria-hidden />
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              )
            })
          )}
        </ul>
      )}
    </article>
  )
}
