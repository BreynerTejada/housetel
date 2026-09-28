import { Globe, Minus, Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useEffect, useId, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyInput } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useActiveProperty } from '@/lib/auth'
import { formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  normalizeOnboarding,
  useAmenityNames,
  type ChargeType,
  type Proposal,
  type ProposalResponse,
  type ProposalRoomType,
  type RoomKind,
} from '../../api'
import { KeyTags } from './KeyTags'
import {
  MAX_UNITS,
  clampInt,
  needsNumbers,
  newExtra,
  newRoomType,
  planCodes,
  problems,
  totalRooms,
  withCapacity,
  withDormBeds,
  withKind,
} from './proposal'

const CHARGE_TYPES: ChargeType[] = ['per_stay', 'per_night', 'per_person', 'per_person_night']
const NO_STARS = 'none'

type SetProposal = Dispatch<SetStateAction<Proposal>>

/** Takes the numbers (and the units they were generated for) the backend assigned; keeps what the user typed. */
function mergeNumbers(current: Proposal, normalized: Proposal): Proposal {
  if (normalized.room_types.length !== current.room_types.length) return current
  return {
    ...current,
    room_types: current.room_types.map((item, index) => {
      const fixed = normalized.room_types[index]
      if (!fixed) return item
      return {
        ...item,
        units: fixed.units,
        room_numbers: fixed.room_numbers,
        code: item.code.trim() ? item.code : fixed.code,
        beds_per_room: item.kind === 'dorm' ? fixed.beds_per_room : item.beds_per_room,
      }
    }),
  }
}

/** Keeps room numbers unique in the hotel: rows whose units or kind changed get numbers from the backend. */
function useRoomNumbers(proposal: Proposal, setProposal: SetProposal): boolean {
  const [busy, setBusy] = useState(false)
  const latest = useRef(proposal)
  const request = useRef(0)

  useEffect(() => {
    latest.current = proposal
  })

  useEffect(() => {
    if (!proposal.room_types.some(needsNumbers)) return
    const id = ++request.current
    const timer = window.setTimeout(async () => {
      setBusy(true)
      const current = latest.current
      const body = {
        ...current,
        room_types: current.room_types.map((item) => (needsNumbers(item) ? { ...item, room_numbers: [] } : item)),
      }
      try {
        const result = await normalizeOnboarding(body)
        if (id === request.current) setProposal((value) => mergeNumbers(value, result.proposal))
      } catch {
        // The numbers stay as they are: "Create everything" validates them again on the server.
      } finally {
        if (id === request.current) setBusy(false)
      }
    }, 450)
    return () => window.clearTimeout(timer)
  }, [proposal, setProposal])

  return busy
}

function Field({ label, className, children }: { label: ReactNode; className?: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className={cn('grid content-start gap-1.5', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
    </div>
  )
}

/** Whole number with − / + buttons; what is typed is committed (clamped) on blur or Enter. */
function NumberField({
  id,
  value,
  min,
  max,
  onChange,
  suffix,
}: {
  id: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
  suffix?: string
}) {
  const { t } = useTranslation('ai')
  const [draft, setDraft] = useState<string | null>(null)
  const commit = () => {
    if (draft !== null) onChange(clampInt(draft, min, max, value))
    setDraft(null)
  }
  return (
    <div className="flex h-9 items-stretch overflow-hidden rounded-md border border-border bg-surface shadow-xs focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/15">
      <button
        type="button"
        aria-label={t('onboarding.less')}
        disabled={value <= min}
        onClick={() => onChange(Math.max(min, value - 1))}
        className="grid w-8 shrink-0 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-fg disabled:opacity-40"
      >
        <Minus aria-hidden className="size-3.5" />
      </button>
      <input
        id={id}
        inputMode="numeric"
        value={draft ?? String(value)}
        onChange={(event) => setDraft(event.target.value.replace(/[^\d-]/g, ''))}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            commit()
          }
        }}
        className="num w-full min-w-0 bg-transparent text-center text-sm font-semibold text-fg outline-none"
      />
      {suffix && <span className="grid place-items-center pr-1 text-xs text-muted">{suffix}</span>}
      <button
        type="button"
        aria-label={t('onboarding.more')}
        disabled={value >= max}
        onClick={() => onChange(Math.min(max, value + 1))}
        className="grid w-8 shrink-0 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-fg disabled:opacity-40"
      >
        <Plus aria-hidden className="size-3.5" />
      </button>
    </div>
  )
}

function Section({ title, description, action, children }: { title: string; description?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent className="pt-4">{children}</CardContent>
    </Card>
  )
}

export function ReviewStep({
  proposal,
  setProposal,
  response,
  onBack,
  onApply,
  applying,
  applyError,
}: {
  proposal: Proposal
  setProposal: SetProposal
  response: ProposalResponse
  onBack: () => void
  onApply: () => void
  applying: boolean
  applyError: string | null
}) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const currency = property?.currency ?? 'COP'
  const renumbering = useRoomNumbers(proposal, setProposal)
  const amenities = useAmenityNames()
  const blocking = problems(proposal)
  const plans = planCodes(proposal)
  const prices = proposal.room_types.map((item) => Number(item.base_price)).filter((price) => price > 0)

  const setHotel = (patch: Partial<Proposal['property']>) =>
    setProposal((current) => ({ ...current, property: { ...current.property, ...patch } }))
  const setPolicies = (patch: Partial<Proposal['policies']>) =>
    setProposal((current) => ({ ...current, policies: { ...current.policies, ...patch } }))
  const setRoomType = (index: number, update: (item: ProposalRoomType) => ProposalRoomType) =>
    setProposal((current) => ({
      ...current,
      room_types: current.room_types.map((item, i) => (i === index ? update(item) : item)),
    }))
  const setExtra = (index: number, patch: Partial<Proposal['extras'][number]>) =>
    setProposal((current) => ({
      ...current,
      extras: current.extras.map((extra, i) => (i === index ? { ...extra, ...patch } : extra)),
    }))
  const amenityName = (code: string) => amenities.data?.get(code)?.[lang] || code.replace(/_/g, ' ')

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_19rem] xl:items-start">
      <div className="grid min-w-0 gap-6">
        <div className="grid gap-3">
          <div>
            <h2 className="text-lg font-bold text-fg">{t('onboarding.reviewTitle')}</h2>
            <p className="text-sm text-muted">{t('onboarding.reviewText')}</p>
          </div>
          {response.simulated && (
            <p className="rounded-lg bg-warning-soft px-3.5 py-2.5 text-[13px] text-warning-ink">{t('onboarding.simulated')}</p>
          )}
          {response.website?.fetched && (
            <p className="flex items-center gap-2 text-[13px] text-muted">
              <Globe aria-hidden className="size-4 text-subtle" />
              {t('onboarding.websiteRead', { chars: response.website.chars.toLocaleString(lang), url: response.website.url })}
            </p>
          )}
          {response.warnings.length > 0 && (
            <div className="rounded-lg border border-border bg-surface px-3.5 py-2.5 text-[13px]">
              <p className="flex items-center gap-1.5 font-bold text-warning-ink">
                <TriangleAlert aria-hidden className="size-4" />
                {t('onboarding.warnings')}
              </p>
              <ul className="mt-1 list-disc pl-5 text-muted">
                {response.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <Section title={t('onboarding.hotel')}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={t('onboarding.name')} className="sm:col-span-2">
              {(id) => (
                <Input id={id} name="hotel-name" value={proposal.property.name} onChange={(event) => setHotel({ name: event.target.value })} />
              )}
            </Field>
            <Field label={t('onboarding.city')} className="sm:col-span-2">
              {(id) => <Input id={id} name="hotel-city" value={proposal.property.city} onChange={(event) => setHotel({ city: event.target.value })} />}
            </Field>
            <Field label={t('onboarding.checkIn')}>
              {(id) => (
                <Input
                  id={id}
                  name="check-in"
                  type="time"
                  value={proposal.property.check_in_time ?? ''}
                  onChange={(event) => setHotel({ check_in_time: event.target.value || null })}
                />
              )}
            </Field>
            <Field label={t('onboarding.checkOut')}>
              {(id) => (
                <Input
                  id={id}
                  name="check-out"
                  type="time"
                  value={proposal.property.check_out_time ?? ''}
                  onChange={(event) => setHotel({ check_out_time: event.target.value || null })}
                />
              )}
            </Field>
            <Field label={t('onboarding.stars')} className="sm:col-span-2">
              {(id) => (
                <Select
                  name="stars"
                  value={proposal.property.star_rating ? String(proposal.property.star_rating) : NO_STARS}
                  onValueChange={(value) => setHotel({ star_rating: value === NO_STARS ? null : Number(value) })}
                >
                  <SelectTrigger id={id}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_STARS}>{t('onboarding.noStars')}</SelectItem>
                    {[1, 2, 3, 4, 5].map((stars) => (
                      <SelectItem key={stars} value={String(stars)}>
                        {'★'.repeat(stars)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </Field>
            <Field label={t('onboarding.descriptionLabel')} className="sm:col-span-2 lg:col-span-4">
              {(id) => (
                <Textarea
                  id={id}
                  name="hotel-description"
                  rows={3}
                  value={proposal.property.description.es}
                  onChange={(event) => setHotel({ description: { ...proposal.property.description, es: event.target.value } })}
                />
              )}
            </Field>
            {proposal.property.amenities.length > 0 && (
              <div className="grid gap-1.5 sm:col-span-2 lg:col-span-4">
                <p className="text-[13px] font-semibold text-fg">{t('onboarding.amenities')}</p>
                <ul className="flex flex-wrap gap-1.5">
                  {proposal.property.amenities.map((code) => (
                    <li key={code}>
                      <Badge tone="neutral">{amenityName(code)}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Section>

        <Section
          title={t('onboarding.roomTypes')}
          description={t('onboarding.roomTypesHint')}
          action={
            <Button size="sm" onClick={() => setProposal((current) => ({ ...current, room_types: [...current.room_types, newRoomType()] }))}>
              <Plus aria-hidden />
              {t('onboarding.addRoomType')}
            </Button>
          }
        >
          {proposal.room_types.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border-strong px-4 py-6 text-center text-sm text-muted">
              {t('onboarding.noRoomTypes')}
            </p>
          ) : (
            <ol className="grid gap-4">
              {proposal.room_types.map((item, index) => (
                <RoomTypeCard
                  key={index}
                  item={item}
                  currency={currency}
                  renumbering={renumbering && needsNumbers(item)}
                  amenityName={amenityName}
                  onChange={(update) => setRoomType(index, update)}
                  onRemove={() =>
                    setProposal((current) => ({ ...current, room_types: current.room_types.filter((_, i) => i !== index) }))
                  }
                />
              ))}
            </ol>
          )}
        </Section>

        <Section title={t('onboarding.policies')}>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label={t('onboarding.nrDiscount')}>
              {(id) => (
                <NumberField
                  id={id}
                  value={proposal.policies.non_refundable_discount_percent}
                  min={0}
                  max={90}
                  suffix="%"
                  onChange={(value) => setPolicies({ non_refundable_discount_percent: value })}
                />
              )}
            </Field>
            <Field label={t('onboarding.breakfast')}>
              {(id) => (
                <div className="grid gap-1">
                  <MoneyInput
                    id={id}
                    name="breakfast-price"
                    currency={currency}
                    value={proposal.policies.breakfast_price ?? ''}
                    onChange={(value) => setPolicies({ breakfast_price: value || null })}
                  />
                  <p className="text-xs text-muted">{t('onboarding.breakfastHint')}</p>
                </div>
              )}
            </Field>
            <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
              {(['pets_allowed', 'smoking_allowed', 'children_allowed'] as const).map((key) => (
                <SwitchRow
                  key={key}
                  label={t(`onboarding.${key === 'pets_allowed' ? 'pets' : key === 'smoking_allowed' ? 'smoking' : 'children'}`)}
                  checked={proposal.policies[key]}
                  onCheckedChange={(checked) => setPolicies({ [key]: checked })}
                />
              ))}
            </div>
          </div>
        </Section>

        <Section
          title={t('onboarding.extras')}
          action={
            <Button size="sm" onClick={() => setProposal((current) => ({ ...current, extras: [...current.extras, newExtra()] }))}>
              <Plus aria-hidden />
              {t('onboarding.addExtra')}
            </Button>
          }
        >
          {proposal.extras.length === 0 ? (
            <p className="text-sm text-muted">{t('onboarding.noExtras')}</p>
          ) : (
            <ul className="grid gap-3">
              {proposal.extras.map((extra, index) => (
                <li
                  key={index}
                  className="grid gap-2 border-b border-border pb-3 last:border-0 last:pb-0 sm:grid-cols-[minmax(0,1fr)_9rem_12rem_auto] sm:items-end"
                >
                  <div className="flex items-end gap-2 sm:contents">
                    <Field label={t('onboarding.extraName')} className="min-w-0 flex-1">
                      {(id) => (
                        <Input
                          id={id}
                          name={`extra-${index}-name`}
                          value={extra.name.es}
                          aria-invalid={!extra.name.es.trim() || undefined}
                          onChange={(event) => setExtra(index, { name: { ...extra.name, es: event.target.value } })}
                        />
                      )}
                    </Field>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 sm:order-last"
                      aria-label={t('onboarding.removeExtra', { name: extra.name.es || t('onboarding.extraName') })}
                      onClick={() => setProposal((current) => ({ ...current, extras: current.extras.filter((_, i) => i !== index) }))}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:contents">
                    <Field label={t('onboarding.extraPrice')}>
                      {(id) => (
                        <MoneyInput
                          id={id}
                          name={`extra-${index}-price`}
                          currency={currency}
                          value={extra.price}
                          aria-invalid={!(Number(extra.price) > 0) || undefined}
                          onChange={(value) => setExtra(index, { price: value })}
                        />
                      )}
                    </Field>
                    <Field label={t('onboarding.chargeType')}>
                      {(id) => (
                        <Select name={`extra-${index}-charge`} value={extra.charge_type} onValueChange={(value) => setExtra(index, { charge_type: value as ChargeType })}>
                          <SelectTrigger id={id}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CHARGE_TYPES.map((type) => (
                              <SelectItem key={type} value={type}>
                                {t(`onboarding.${type}`)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </Field>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <aside className="min-w-0 xl:sticky xl:top-20">
        <Card>
          <CardContent className="grid gap-4 py-5">
            <p className="eyebrow">{t('onboarding.summary')}</p>
            <p className="text-[15px] leading-6 font-bold text-fg">
              {t('onboarding.summaryTypes', { count: proposal.room_types.length })} ·{' '}
              {t('onboarding.summaryRooms', { count: totalRooms(proposal) })}
            </p>
            {prices.length > 0 && (
              <p className="num -mt-2 text-[13px] text-muted">
                {t('onboarding.summaryPrices', {
                  min: formatMoney(String(Math.min(...prices)), currency),
                  max: formatMoney(String(Math.max(...prices)), currency),
                })}
              </p>
            )}
            <div className="grid gap-1.5">
              <p className="text-[13px] font-semibold text-fg">{t('onboarding.summaryPlans')}</p>
              <ul className="flex flex-wrap gap-1.5">
                {plans.map((code) => (
                  <li key={code}>
                    <Badge tone={code === 'FLEX' ? 'accent' : 'neutral'}>
                      {t(`onboarding.plan${code}`, {
                        discount: proposal.policies.non_refundable_discount_percent,
                        price: formatMoney(proposal.policies.breakfast_price ?? '0', currency),
                      })}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
            <p className="text-[13px] text-muted">{t('onboarding.summaryExtras', { count: proposal.extras.length })}</p>
            {blocking.length > 0 && (
              <ul className="grid gap-1 rounded-md bg-warning-soft px-3 py-2 text-[12.5px] text-warning-ink">
                {blocking.map((key) => (
                  <li key={key}>{t(key)}</li>
                ))}
              </ul>
            )}
            {applyError && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[12.5px] text-danger-ink">
                {applyError}
              </p>
            )}
            <div className="grid gap-2">
              <Button variant="primary" loading={applying} disabled={blocking.length > 0 || renumbering || applying} onClick={onApply}>
                {applying ? t('onboarding.applying') : t('onboarding.apply')}
              </Button>
              <Button variant="ghost" disabled={applying} onClick={onBack}>
                {t('onboarding.back')}
              </Button>
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

function SwitchRow({ label, checked, onCheckedChange }: { label: string; checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
      <Label htmlFor={id} className="font-medium">
        {label}
      </Label>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
}

function RoomTypeCard({
  item,
  currency,
  renumbering,
  amenityName,
  onChange,
  onRemove,
}: {
  item: ProposalRoomType
  currency: string
  renumbering: boolean
  amenityName: (code: string) => string
  onChange: (update: (item: ProposalRoomType) => ProposalRoomType) => void
  onRemove: () => void
}) {
  const { t } = useTranslation('ai')
  const dorm = item.kind === 'dorm'
  const name = item.name.es.trim() || t('onboarding.untitledType')
  return (
    <li className="overflow-hidden rounded-lg border border-border bg-bg">
      <div className="grid gap-4 p-4">
        <div className="flex items-start gap-3">
          <div className="grid min-w-0 flex-1 gap-4 sm:grid-cols-2">
            <Field label={t('onboarding.typeName')}>
              {(id) => (
                <Input
                  id={id}
                  name="room-type-name"
                  value={item.name.es}
                  aria-invalid={!item.name.es.trim() || undefined}
                  onChange={(event) => onChange((current) => ({ ...current, name: { ...current.name, es: event.target.value } }))}
                />
              )}
            </Field>
            <Field label={t('onboarding.typeNameEn')}>
              {(id) => (
                <Input
                  id={id}
                  name="room-type-name-en"
                  value={item.name.en}
                  onChange={(event) => onChange((current) => ({ ...current, name: { ...current.name, en: event.target.value } }))}
                />
              )}
            </Field>
          </div>
          <Button variant="ghost" size="icon" className="mt-6 shrink-0" aria-label={t('onboarding.removeRoomType', { name })} onClick={onRemove}>
            <Trash2 aria-hidden />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label={t('onboarding.code')}>
            {(id) => (
              <Input
                id={id}
                name="room-type-code"
                value={item.code}
                maxLength={20}
                className="num uppercase"
                onChange={(event) => onChange((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
              />
            )}
          </Field>
          <Field label={t('onboarding.kind')}>
            {(id) => (
              <Select name="room-type-kind" value={item.kind} onValueChange={(value) => onChange((current) => withKind(current, value as RoomKind))}>
                <SelectTrigger id={id}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">{t('onboarding.private')}</SelectItem>
                  <SelectItem value="dorm">{t('onboarding.dorm')}</SelectItem>
                </SelectContent>
              </Select>
            )}
          </Field>
          <Field label={dorm ? t('onboarding.dormUnits') : t('onboarding.units')}>
            {(id) => (
              <NumberField id={id} value={item.units} min={1} max={MAX_UNITS} onChange={(units) => onChange((current) => ({ ...current, units }))} />
            )}
          </Field>
          <Field label={dorm ? t('onboarding.bedsPerRoom') : t('onboarding.capacity')}>
            {(id) =>
              dorm ? (
                <NumberField
                  id={id}
                  value={item.beds_per_room ?? 6}
                  min={1}
                  max={40}
                  onChange={(beds) => onChange((current) => withDormBeds(current, beds))}
                />
              ) : (
                <NumberField id={id} value={item.max_occupancy} min={1} max={20} onChange={(guests) => onChange((current) => withCapacity(current, guests))} />
              )
            }
          </Field>
          <Field label={dorm ? t('onboarding.pricePerBed') : t('onboarding.price')}>
            {(id) => (
              <MoneyInput
                id={id}
                name="room-type-price"
                currency={currency}
                value={item.base_price}
                aria-invalid={!(Number(item.base_price) > 0) || undefined}
                onChange={(value) => onChange((current) => ({ ...current, base_price: value }))}
              />
            )}
          </Field>
          <Field label={t('onboarding.weekend')}>
            {(id) => (
              <NumberField
                id={id}
                value={item.weekend_adjust_percent}
                min={-50}
                max={200}
                suffix="%"
                onChange={(value) => onChange((current) => ({ ...current, weekend_adjust_percent: value }))}
              />
            )}
          </Field>
        </div>

        {item.amenities.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label={t('onboarding.amenities')}>
            {item.amenities.map((code) => (
              <li key={code}>
                <Badge tone="neutral">{amenityName(code)}</Badge>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid gap-2 border-t border-border bg-surface px-4 py-3">
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
          <span className="eyebrow">{t('onboarding.rooms')}</span>
          <span className="num">{item.room_numbers.length}</span>
          {dorm && <span>· {t('onboarding.bedsEach', { count: item.beds_per_room ?? 0 })}</span>}
          {renumbering && <span aria-live="polite">· {t('onboarding.renumbering')}</span>}
        </p>
        <KeyTags rooms={item.room_numbers} busy={renumbering} label={t('onboarding.keyRackLabel', { name, rooms: item.room_numbers.join(', ') })} />
      </div>
    </li>
  )
}
