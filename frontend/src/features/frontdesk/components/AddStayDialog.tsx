import { useQueryClient } from '@tanstack/react-query'
import { BedDouble } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DateRangePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  addStay,
  bookingKeys,
  useGroup,
  useRefreshFrontDesk,
  useRoomOffers,
  useStaysQuote,
  type ReservationDetail,
  type RoomOffer,
  type StayRequestInput,
} from '../api'
import { tr } from '../lib/labels'
import { offerKey } from '../lib/wizard'
import { Counter } from './Counter'

const AGES = Array.from({ length: 18 }, (_, age) => age)

/**
 * Add a room to an existing reservation (pilot P3): the dates (the reservation's by default), an offer per room
 * for them, its guests and the exact price before saving (`reservations/quote/` → `reservations/{id}/stays/`).
 * A dorm adds one bed per guest. A reservation of a group with an open allotment can take the room from it.
 */
export function AddStayDialog({
  open,
  onOpenChange,
  reservation,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  reservation: ReservationDetail
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? reservation.checkin_date
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const ids = { dates: useId(), offers: useId(), source: useId() }
  const lang = normalizeLang(i18n.language)
  const startDefault = reservation.checkin_date < bd ? bd : reservation.checkin_date
  const [range, setRange] = useState({ from: startDefault, to: reservation.checkout_date > startDefault ? reservation.checkout_date : startDefault })
  const [picked, setPicked] = useState<string | null>(null)
  const [adults, setAdults] = useState(2)
  const [children, setChildren] = useState(0)
  const [ages, setAges] = useState<(number | null)[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [blockId, setBlockId] = useState<string | null>(null)
  const group = useGroup(open ? reservation.group?.id : null)
  const blocks = (group.data?.blocks ?? []).filter((block) => !block.released_at && block.end > bd)
  const foreign = reservation.booker.is_foreign_non_resident
  const offers = useRoomOffers({ checkin: range.from, checkout: range.to, promoCode: reservation.promo_code, foreign, block: blockId }, open)
  const offer = offers.data?.find((item) => offerKey(item.room_type_id, item.rate_plan_id) === picked)
  const dorm = offer?.room_type.kind === 'dorm'
  const maxAdults = offer ? (dorm ? Math.max(1, offer.available_units) : offer.room_type.max_adults) : 20
  const maxChildren = offer ? offer.room_type.max_children : 0
  const agesOk = ages.slice(0, children).every((age) => age !== null) && ages.length >= children
  const fits =
    offer &&
    adults + children >= 1 &&
    (dorm ? adults + children <= offer.available_units : adults >= 1 && adults + children <= offer.room_type.max_occupancy)

  const stay: StayRequestInput | null = useMemo(
    () =>
      offer && fits && agesOk
        ? {
            room_type_id: offer.room_type_id,
            rate_plan_id: offer.rate_plan_id,
            checkin: range.from,
            checkout: range.to,
            adults,
            children,
            children_ages: ages.slice(0, children).map((age) => age ?? 0),
            ...(blockId ? { group_block_id: blockId } : {}),
          }
        : null,
    [offer, fits, agesOk, range, adults, children, ages, blockId],
  )
  const quote = useStaysQuote(stay ? { stays: [stay], promo_code: reservation.promo_code, foreign } : null, open)

  function pick(next: RoomOffer) {
    setPicked(offerKey(next.room_type_id, next.rate_plan_id))
    const kindDorm = next.room_type.kind === 'dorm'
    setAdults(kindDorm ? 1 : Math.min(Math.max(1, adults), next.room_type.max_adults))
    if (next.room_type.max_children === 0) {
      setChildren(0)
      setAges([])
    }
  }

  function changeChildren(value: number) {
    setChildren(value)
    setAges((current) => {
      const next = current.slice(0, value)
      while (next.length < value) next.push(null)
      return next
    })
  }

  async function save() {
    if (!stay) return
    setSaving(true)
    setError(null)
    try {
      const detail = await addStay(reservation.id, stay)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(t(dorm ? 'addStay.doneBeds' : 'addStay.done', { count: adults + children, code: reservation.code }))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
      void offers.refetch()
    } finally {
      setSaving(false)
    }
  }

  const groups = new Map<string, RoomOffer[]>()
  for (const item of offers.data ?? []) groups.set(item.room_type_id, [...(groups.get(item.room_type_id) ?? []), item])

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('addStay.title')}</DialogTitle>
          <DialogDescription>{t('addStay.description', { code: reservation.code })}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-5">
          {blocks.length > 0 && (
            <div className="grid gap-2">
              <Label htmlFor={ids.source} className="font-semibold">
                {t('addStay.from')}
              </Label>
              <Select
                value={blockId ?? 'general'}
                onValueChange={(value) => {
                  const block = blocks.find((item) => item.id === value)
                  setBlockId(block ? block.id : null)
                  setPicked(null)
                  if (block) {
                    const from = block.start < bd ? bd : block.start
                    setRange({ from, to: block.end > from ? block.end : range.to })
                  }
                }}
              >
                <SelectTrigger id={ids.source} className="max-w-md">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="general">{t('addStay.fromGeneral')}</SelectItem>
                  {blocks.map((block) => (
                    <SelectItem key={block.id} value={block.id}>
                      {t('addStay.fromBlock', {
                        units: block.units,
                        type: tr(block.room_type.name, i18n.language),
                        dates: formatDateRange(block.start, block.end, lang),
                      })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor={ids.dates} className="font-semibold">
              {t('addStay.dates')}
            </Label>
            <DateRangePicker
              id={ids.dates}
              value={range}
              onChange={(value) => {
                if (!value) return
                setRange({ from: value.from, to: value.to })
                setPicked(null)
              }}
              today={bd}
              min={bd}
              minNights={1}
              showNights
              className="max-w-sm"
            />
          </div>

          <section aria-labelledby={ids.offers} className="grid gap-2">
            <h3 id={ids.offers} className="eyebrow">
              {t('addStay.offer')}
            </h3>
            {offers.isError ? (
              <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
            ) : !offers.data ? (
              <LoadingState variant="rows" rows={2} className="p-0" />
            ) : offers.data.length === 0 ? (
              <EmptyState icon={BedDouble} title={t('wizard.noOffers')} description={t('addStay.noOffersHint')} className="py-6" />
            ) : (
              <div role="radiogroup" aria-labelledby={ids.offers} className="grid max-h-72 gap-3 overflow-y-auto pr-1">
                {[...groups.values()].map((plans) => (
                  <div key={plans[0]!.room_type_id} className="grid gap-1.5">
                    <p className="flex items-center gap-2 text-[13px] font-semibold text-fg">
                      <span aria-hidden className="size-2.5 rounded-[3px]" style={{ backgroundColor: plans[0]!.room_type.color }} />
                      {tr(plans[0]!.room_type.name, i18n.language)}
                      <span className="font-normal text-muted">
                        · {t(plans[0]!.room_type.kind === 'dorm' ? 'wizard.bedsLeft' : 'wizard.roomsLeft', { count: plans[0]!.available_units })}
                      </span>
                    </p>
                    {plans.map((item) => {
                      const key = offerKey(item.room_type_id, item.rate_plan_id)
                      const checked = key === picked
                      return (
                        <label
                          key={key}
                          className={cn(
                            'flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 transition-colors hover:border-border-strong focus-within:ring-2 focus-within:ring-accent/55',
                            checked && 'border-accent bg-accent-soft/40 hover:border-accent',
                          )}
                        >
                          <input type="radio" name={ids.offers} checked={checked} onChange={() => pick(item)} className="size-4 shrink-0 accent-accent" />
                          <span className="min-w-0 flex-1">
                            <span className="block text-[13px] font-semibold text-fg">{tr(item.rate_plan.name, i18n.language)}</span>
                            <span className="block text-xs text-muted">{t(`mealPlans.${item.rate_plan.meal_plan}`, { defaultValue: item.rate_plan.meal_plan })}</span>
                          </span>
                          <span className="text-right">
                            <MoneyText value={item.total} currency={item.quote.currency} className="block text-[13px] font-bold text-fg" />
                            <span className="block text-xs text-muted">{t(item.room_type.kind === 'dorm' ? 'wizard.perBed' : 'wizard.perRoom')}</span>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                ))}
              </div>
            )}
          </section>

          {offer && (
            <section className="grid gap-3 border-t border-border pt-4">
              <Counter
                label={dorm ? t('addStay.beds') : t('wizard.adults')}
                value={adults}
                min={dorm ? 0 : 1}
                max={maxAdults}
                onChange={setAdults}
                addLabel={t('wizard.addAdult')}
                removeLabel={t('wizard.removeAdult')}
              />
              {maxChildren > 0 && (
                <Counter
                  label={t('wizard.children')}
                  hint={t('wizard.childrenHint')}
                  value={children}
                  min={0}
                  max={dorm ? Math.max(0, offer.available_units - adults) : maxChildren}
                  onChange={changeChildren}
                  addLabel={t('wizard.addChild')}
                  removeLabel={t('wizard.removeChild')}
                />
              )}
              {children > 0 && (
                <div className="grid gap-2 sm:grid-cols-3">
                  {ages.slice(0, children).map((age, index) => (
                    <Select
                      key={index}
                      value={age === null ? '' : String(age)}
                      onValueChange={(value) => setAges((current) => current.map((item, position) => (position === index ? Number(value) : item)))}
                    >
                      <SelectTrigger aria-label={t('wizard.childAge', { number: index + 1 })}>
                        <SelectValue placeholder={t('wizard.childAge', { number: index + 1 })} />
                      </SelectTrigger>
                      <SelectContent>
                        {AGES.map((value) => (
                          <SelectItem key={value} value={String(value)}>
                            {value === 0 ? t('wizard.underOne') : t('wizard.years', { count: value })}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ))}
                </div>
              )}
              {!fits && <p className="text-[13px] font-semibold text-danger-ink">{t('addStay.tooMany')}</p>}
              <div className="flex items-baseline justify-between gap-3 rounded-lg bg-surface-2/70 px-4 py-2.5 text-[13px]" aria-live="polite">
                <span className="text-muted">{t('addStay.total')}</span>
                {quote.isError ? (
                  <span className="text-danger-ink">{errorMessage(quote.error, t)}</span>
                ) : quote.data && stay ? (
                  <MoneyText value={quote.data.total} currency={quote.data.currency} className="text-[15px] font-bold text-fg" />
                ) : (
                  <span className="text-muted">—</span>
                )}
              </div>
            </section>
          )}
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={saving} disabled={!stay || !quote.data || quote.isError}>
            {t('addStay.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
