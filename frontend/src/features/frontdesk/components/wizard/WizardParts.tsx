import { Check, DoorOpen, UsersRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { isExistingGuest } from '@/features/guests/api'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, nightsBetween, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Extra, RoomOffer, StaysQuote } from '../../api'
import { guestsLabel, tr } from '../../lib/labels'
import { matchingLine, roomSplit, WIZARD_STEPS, type RoomUnit, type WizardState, type WizardStep } from '../../lib/wizard'

/** The five steps as a numbered path (the order is real: each step needs the previous one). */
export function WizardSteps({ current, reached, onPick }: { current: WizardStep; reached: WizardStep; onPick: (step: WizardStep) => void }) {
  const { t } = useTranslation('frontdesk')
  return (
    <nav aria-label={t('wizard.stepsLabel')} className="mb-5 overflow-x-auto [scrollbar-width:none]">
      <ol className="flex min-w-max items-center gap-1.5">
        {WIZARD_STEPS.map((key, index) => {
          const step = index as WizardStep
          const done = step < current
          const active = step === current
          const reachable = step <= reached && !active
          const content = (
            <>
              <span
                aria-hidden
                className={cn(
                  'num grid size-6 place-items-center rounded-full border text-[11px] font-bold',
                  active && 'border-accent bg-accent text-on-accent',
                  done && 'border-success bg-success-soft text-success-ink',
                  !active && !done && 'border-border-strong text-muted',
                )}
              >
                {done ? <Check className="size-3.5" /> : index + 1}
              </span>
              <span className={cn('text-[13px] font-semibold', active ? 'text-fg' : 'text-muted')}>{t(`wizard.steps.${key}`)}</span>
            </>
          )
          return (
            <li key={key} className="flex items-center gap-1.5">
              {index > 0 && <span aria-hidden className="h-px w-5 bg-border-strong" />}
              {reachable ? (
                <button type="button" onClick={() => onPick(step)} className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-surface-2">
                  {content}
                </button>
              ) : (
                <span aria-current={active ? 'step' : undefined} className="flex items-center gap-2 px-1.5 py-1">
                  {content}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

/** Sticky summary: what is being booked — each room with its guests and price — and what it costs so far. */
export function WizardSummary({
  state,
  units,
  offers,
  quote,
  extras,
  currency,
  groupLabel,
  fromBlock = false,
}: {
  state: WizardState
  units: RoomUnit[]
  offers?: RoomOffer[]
  quote: { data?: StaysQuote; isFetching: boolean; isError: boolean; error: unknown }
  extras: Extra[]
  currency: string
  /** Name of the group (new or existing) when it is a group reservation. */
  groupLabel?: string
  /** The rooms are picked up from the group's allotment. */
  fromBlock?: boolean
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const nights = nightsBetween(state.checkin, state.checkout)
  const extrasTotal = extras.reduce((sum, extra) => sum + Number(extra.price) * (state.extras[extra.id] ?? 0), 0)
  const { split } = roomSplit(state, units)
  const lines = quote.data?.stays
  const priced = units.length > 0 && units.every((unit, index) => matchingLine(lines, index, unit, split[index]!))
  const stayTotal = priced ? Number(quote.data!.total) : 0
  const guest = state.guest
  const guestName = guest ? (isExistingGuest(guest) ? guest.full_name : `${guest.first_name} ${guest.last_name}`.trim()) : null

  return (
    <aside aria-label={t('wizard.summary')} className="rounded-xl border border-border bg-surface p-5 shadow-xs lg:sticky lg:top-20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-bold">{t('wizard.summary')}</h2>
        <div className="flex flex-wrap gap-1.5">
          {groupLabel && (
            <Badge tone="info">
              <UsersRound aria-hidden />
              <span className="max-w-40 truncate">{groupLabel}</span>
            </Badge>
          )}
          {fromBlock && <Badge tone="accent">{t('wizard.group.blockBadge')}</Badge>}
          {state.walkIn && (
            <Badge tone="accent">
              <DoorOpen aria-hidden />
              {t('actions.walkIn')}
            </Badge>
          )}
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-[13px]">
        <div>
          <dt className="text-muted">{t('wizard.summaryStay')}</dt>
          <dd className="num font-semibold text-fg">
            {state.checkin && state.checkout ? formatDateRange(state.checkin, state.checkout, lang) : '—'}
            {nights > 0 && <span className="font-normal text-muted"> · {t('common:date.nights', { count: nights })}</span>}
          </dd>
          <dd className="text-muted">{guestsLabel(t, state.adults, state.children)}</dd>
        </div>
        <div>
          <dt className="text-muted">{units.length > 1 ? t('wizard.summaryRooms', { count: units.length }) : t('wizard.summaryRoom')}</dt>
          {units.length === 0 ? (
            <dd className="font-semibold text-fg">{t('wizard.summaryNoOffer')}</dd>
          ) : (
            <dd>
              <ol className="mt-1 grid gap-1.5">
                {units.map((unit, index) => {
                  const offer = offers?.find((item) => item.room_type_id === unit.roomTypeId && item.rate_plan_id === unit.ratePlanId)
                  const room = split[index]!
                  const line = matchingLine(lines, index, unit, room)
                  return (
                    <li key={unit.key} className="flex items-start justify-between gap-3">
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-fg">
                          <span className="num text-muted">{index + 1}.</span> {offer ? tr(offer.room_type.name, i18n.language) : ''}
                        </span>
                        <span className="block truncate text-xs text-muted">
                          {offer ? tr(offer.rate_plan.name, i18n.language) : ''} · {guestsLabel(t, room.adults, room.children)}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        {line ? (
                          <MoneyText value={line.total} currency={currency} className="font-semibold text-fg" />
                        ) : (
                          <span className="text-muted">{quote.isFetching ? '…' : '—'}</span>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ol>
            </dd>
          )}
        </div>
        <div>
          <dt className="text-muted">{t('wizard.summaryGuest')}</dt>
          <dd className="font-semibold text-fg">{guestName || t('wizard.summaryNoGuest')}</dd>
        </div>
      </dl>
      {quote.isError && units.length > 0 && (
        <p role="alert" className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-xs text-danger-ink">
          {errorMessage(quote.error, t)}
        </p>
      )}
      <dl className="mt-4 grid gap-1.5 border-t border-border pt-4 text-[13px]">
        <div className="flex justify-between gap-3">
          <dt className="text-muted">{t('wizard.summaryStayTotal')}</dt>
          <dd>{priced ? <MoneyText value={stayTotal} currency={currency} /> : <span className="text-muted">—</span>}</dd>
        </div>
        {extrasTotal > 0 && (
          <div className="flex justify-between gap-3">
            <dt className="text-muted">{t('wizard.summaryExtras')}</dt>
            <dd>
              <MoneyText value={extrasTotal} currency={currency} />
            </dd>
          </div>
        )}
        <div className="flex justify-between gap-3 pt-1 text-[15px] font-bold text-fg">
          <dt>{t('wizard.summaryTotal')}</dt>
          <dd>
            <MoneyText value={stayTotal + extrasTotal} currency={currency} />
          </dd>
        </div>
        {extrasTotal > 0 && <p className="text-xs text-muted">{t('wizard.summaryExtrasTax')}</p>}
      </dl>
    </aside>
  )
}
