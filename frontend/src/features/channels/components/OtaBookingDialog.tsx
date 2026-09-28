import { Shuffle, TriangleAlert } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  createSimBooking,
  modifySimBooking,
  useChannelsMutation,
  useSimInventory,
  type Connection,
  type OtaBooking,
  type OtaBookingInput,
  type OtaCell,
  type OtaInventory,
} from '../api'
import { addDaysISO, otaQuote, type OtaProblem, type OtaQuote } from '../lib/channels'
import { GUEST_COUNTRIES } from '../lib/labels'
import { tr } from '../lib/text'

export interface OtaBookingPreset {
  room: string
  rate: string
  checkin: string
  checkout: string
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  connection: Connection
  /** Business date of the property. */
  today: string
  currency: string
  /** Change this booking (a new revision); otherwise a new booking. */
  booking?: OtaBooking | null
  preset?: OtaBookingPreset | null
  /** Kind of each PMS category (dorms sell one bed per guest). */
  roomKinds: Record<string, 'private' | 'dorm'>
  onDone: (booking: OtaBooking, created: boolean) => void
}

function countryName(code: string, lang: Lang): string {
  try {
    return new Intl.DisplayNames([lang], { type: 'region' }).of(code) ?? code
  } catch {
    return code
  }
}

/**
 * A guest books (or changes a booking) in the simulated OTA. The OTA only sells what Housetel pushed to it, so
 * the preview reads the same cells; when the OTA refuses, the reasons are listed and the booking can still be
 * forced through to simulate an overbooking. Mount it with a new `key` every time it opens.
 */
export function OtaBookingDialog({ open, onOpenChange, connection, today, currency, booking, preset, roomKinds, onDone }: Props) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const id = useId()
  const current = booking?.payload.rooms[0]
  const rooms = connection.room_mappings.filter((mapping) => !mapping.room && mapping.external_room_id)

  const [roomId, setRoomId] = useState(current?.external_room_id ?? preset?.room ?? rooms[0]?.external_room_id ?? '')
  const mapping = rooms.find((item) => item.external_room_id === roomId)
  const rates = connection.rate_mappings.filter(
    (rate) => rate.external_rate_id && (!rate.room_type || rate.room_type === mapping?.room_type),
  )
  const [rateId, setRateId] = useState(current?.external_rate_id ?? preset?.rate ?? rates[0]?.external_rate_id ?? '')
  const [range, setRange] = useState<{ from: string; to: string } | null>(
    current
      ? { from: current.checkin, to: current.checkout }
      : preset
        ? { from: preset.checkin, to: preset.checkout }
        : { from: addDaysISO(today, 7), to: addDaysISO(today, 9) },
  )
  const [adults, setAdults] = useState(String(current?.adults ?? 2))
  const [children, setChildren] = useState(String(current?.children ?? 0))
  const [guest, setGuest] = useState({ first_name: '', last_name: '', email: '', country: '' })
  const [notes, setNotes] = useState('')
  const [refusal, setRefusal] = useState<string[] | null>(null)

  const effectiveRate = rates.some((rate) => rate.external_rate_id === rateId) ? rateId : (rates[0]?.external_rate_id ?? '')
  const adultsCount = Math.max(0, Math.floor(Number(adults) || 0))
  const childrenCount = Math.max(0, Math.floor(Number(children) || 0))
  const dorm = mapping ? roomKinds[mapping.room_type] === 'dorm' : false
  const units = dorm ? adultsCount + childrenCount : 1
  const valid = Boolean(roomId && effectiveRate && range && range.from < range.to && adultsCount >= 1)

  const previewQuery = useSimInventory(connection.id, range?.from ?? '', range ? addDaysISO(range.to, 1) : '', { enabled: open && valid })
  const quote = previewQuote(previewQuery.data, range, roomId, effectiveRate, units)

  const save = useChannelsMutation(
    (force: boolean) => {
      if (!range) throw new Error('missing range')
      const stay = {
        external_room_id: roomId,
        external_rate_id: effectiveRate,
        checkin: range.from,
        checkout: range.to,
        adults: adultsCount,
        children: childrenCount,
        force,
      }
      if (booking) return modifySimBooking(connection.id, booking.external_id, stay)
      const input: OtaBookingInput = { ...stay, notes: notes.trim() }
      const filled = Object.fromEntries(Object.entries(guest).filter(([, value]) => value.trim()))
      if (Object.keys(filled).length) input.guest = filled
      return createSimBooking(connection.id, input)
    },
    { onSuccess: (result) => onDone(result, !booking) },
  )

  function submit(force: boolean) {
    setRefusal(null)
    save.mutate(force, {
      onError: (error) => {
        if (isApiError(error) && error.code === 'ota_not_sellable') {
          const reasons = (error.data as { reasons?: string[] } | undefined)?.reasons
          setRefusal(reasons?.length ? reasons : [error.message])
        }
      },
    })
  }

  const saveError = save.isError && !(isApiError(save.error) && save.error.code === 'ota_not_sellable') ? save.error : null
  const title = booking ? t('otaBooking.modifyTitle', { id: booking.external_id }) : t('otaBooking.createTitle', { ota: connection.name })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{booking ? t('otaBooking.modifyHint') : t('otaBooking.createHint', { ota: connection.name })}</DialogDescription>
        </DialogHeader>

        <form
          id={`${id}-form`}
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) submit(false)
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FieldBox label={t('otaBooking.room')} htmlFor={`${id}-room`}>
              <Select value={roomId} onValueChange={setRoomId}>
                <SelectTrigger id={`${id}-room`}>
                  <SelectValue placeholder={t('wizard.choose')} />
                </SelectTrigger>
                <SelectContent>
                  {rooms.map((item) => (
                    <SelectItem key={item.id} value={item.external_room_id}>
                      {item.external_room_id} · {tr(item.room_type_name, lang)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldBox>
            <FieldBox label={t('otaBooking.rate')} htmlFor={`${id}-rate`}>
              <Select value={effectiveRate} onValueChange={setRateId} disabled={!rates.length}>
                <SelectTrigger id={`${id}-rate`}>
                  <SelectValue placeholder={t('otaBooking.noRates')} />
                </SelectTrigger>
                <SelectContent>
                  {rates.map((rate) => (
                    <SelectItem key={rate.id} value={rate.external_rate_id}>
                      {rate.external_rate_id} · {tr(rate.rate_plan_name, lang) || t('ota.noPlan')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldBox>
          </div>

          <FieldBox label={t('otaBooking.dates')} htmlFor={`${id}-dates`}>
            <DateRangePicker
              id={`${id}-dates`}
              value={range}
              onChange={setRange}
              today={today}
              min={today}
              minNights={1}
              showNights
              numberOfMonths={1}
            />
          </FieldBox>

          <div className="grid grid-cols-2 gap-4">
            <FieldBox label={t('otaBooking.adults')} htmlFor={`${id}-adults`}>
              <Input id={`${id}-adults`} type="number" inputMode="numeric" min={1} max={20} value={adults} onChange={(event) => setAdults(event.target.value)} />
            </FieldBox>
            <FieldBox label={t('otaBooking.children')} htmlFor={`${id}-children`}>
              <Input id={`${id}-children`} type="number" inputMode="numeric" min={0} max={20} value={children} onChange={(event) => setChildren(event.target.value)} />
            </FieldBox>
          </div>
          {dorm && <p className="-mt-2 text-xs text-muted">{t('otaBooking.dormHint', { count: units })}</p>}

          {!booking && (
            <fieldset className="grid gap-3 rounded-lg border border-border p-3">
              <legend className="px-1 text-[13px] font-semibold text-fg">{t('otaBooking.guest')}</legend>
              <p className="flex items-start gap-2 text-xs text-muted">
                <Shuffle aria-hidden className="mt-0.5 size-3.5 shrink-0" /> {t('otaBooking.guestHint')}
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  aria-label={t('otaBooking.firstName')}
                  placeholder={t('otaBooking.firstName')}
                  value={guest.first_name}
                  maxLength={100}
                  onChange={(event) => setGuest({ ...guest, first_name: event.target.value })}
                />
                <Input
                  aria-label={t('otaBooking.lastName')}
                  placeholder={t('otaBooking.lastName')}
                  value={guest.last_name}
                  maxLength={100}
                  onChange={(event) => setGuest({ ...guest, last_name: event.target.value })}
                />
                <Input
                  type="email"
                  aria-label={t('otaBooking.email')}
                  placeholder={t('otaBooking.email')}
                  value={guest.email}
                  onChange={(event) => setGuest({ ...guest, email: event.target.value })}
                />
                <Select value={guest.country || '__none'} onValueChange={(value) => setGuest({ ...guest, country: value === '__none' ? '' : value })}>
                  <SelectTrigger aria-label={t('otaBooking.country')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">{t('otaBooking.anyCountry')}</SelectItem>
                    {GUEST_COUNTRIES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {countryName(code, lang)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Input aria-label={t('otaBooking.notes')} placeholder={t('otaBooking.notes')} value={notes} maxLength={1000} onChange={(event) => setNotes(event.target.value)} />
            </fieldset>
          )}

          <Preview quote={quote} loading={valid && previewQuery.isFetching && !quote} currency={currency} lang={lang} t={t} />

          {refusal && (
            <div role="alert" className="grid gap-2 rounded-lg bg-warning-soft px-4 py-3 text-[13px] text-warning-ink">
              <p className="flex items-start gap-2 font-semibold">
                <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" /> {t('otaBooking.refused', { ota: connection.name })}
              </p>
              <ul className="grid list-disc gap-0.5 pl-10">
                {refusal.map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
              <p className="text-xs">{t('otaBooking.forceHint')}</p>
            </div>
          )}
          {saveError && (
            <p role="alert" className="rounded-lg bg-danger-soft px-4 py-3 text-[13px] text-danger-ink">
              {errorMessage(saveError, t)}
            </p>
          )}
        </form>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={save.isPending}>
            {t('otaBooking.close')}
          </Button>
          {refusal ? (
            <Button variant="danger" onClick={() => submit(true)} loading={save.isPending}>
              {t('otaBooking.force')}
            </Button>
          ) : (
            <Button variant="primary" type="submit" form={`${id}-form`} disabled={!valid} loading={save.isPending}>
              {booking ? t('otaBooking.saveChange') : t('otaBooking.book', { ota: connection.name })}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FieldBox({ label, htmlFor, children }: { label: ReactNode; htmlFor: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

function problemText(t: TFunction, problem: OtaProblem, lang: Lang): string {
  const day = 'date' in problem ? formatDate(problem.date, 'EEE d MMM', lang) : ''
  switch (problem.code) {
    case 'missing':
      return t('otaBooking.problems.missing', { date: day })
    case 'closed':
      return t('otaBooking.problems.closed', { date: day })
    case 'soldOut':
      return t('otaBooking.problems.soldOut', { date: day, count: problem.available })
    case 'cta':
      return t('otaBooking.problems.cta', { date: day })
    case 'ctd':
      return t('otaBooking.problems.ctd', { date: day })
    case 'minLos':
      return t('otaBooking.problems.minLos', { count: problem.nights })
    case 'maxLos':
      return t('otaBooking.problems.maxLos', { count: problem.nights })
  }
}

function Preview({
  quote,
  loading,
  currency,
  lang,
  t,
}: {
  quote: OtaQuote | null
  loading: boolean
  currency: string
  lang: Lang
  t: TFunction
}) {
  if (loading) return <p className="text-xs text-muted">{t('otaBooking.checking')}</p>
  if (!quote) return null
  const ok = quote.problems.length === 0
  return (
    <section
      aria-live="polite"
      className={cn('grid gap-2 rounded-lg border px-4 py-3', ok ? 'border-success/40 bg-success-soft/50' : 'border-warning/40 bg-warning-soft/50')}
    >
      <p className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className={cn('font-semibold', ok ? 'text-success-ink' : 'text-warning-ink')}>
          {ok ? t('otaBooking.sellable', { count: quote.nights.length }) : t('otaBooking.notSellable')}
        </span>
        {quote.total && <span className="num text-[15px] font-bold text-fg">{formatMoney(quote.total, currency)}</span>}
      </p>
      {!ok && (
        <ul className="grid gap-0.5 text-xs text-warning-ink">
          {quote.problems.slice(0, 4).map((problem, index) => (
            <li key={index}>· {problemText(t, problem, lang)}</li>
          ))}
          {quote.problems.length > 4 && <li>· {t('otaBooking.moreProblems', { count: quote.problems.length - 4 })}</li>}
        </ul>
      )}
    </section>
  )
}

/** What the OTA would charge for the stay, from the cells of the preview fetch (null until they match). */
function previewQuote(
  inventory: OtaInventory | undefined,
  range: { from: string; to: string } | null,
  roomId: string,
  rateId: string,
  units: number,
): OtaQuote | null {
  if (!range || !inventory || inventory.start !== range.from) return null
  const room = inventory.rooms.find((item) => item.external_room_id === roomId)
  const rate = room?.rates.find((item) => item.external_rate_id === rateId)
  const cells: Record<string, OtaCell | null> = {}
  inventory.dates.forEach((date, index) => {
    cells[date] = rate?.cells[index] ?? null
  })
  return otaQuote(cells, range.from, range.to, units)
}
