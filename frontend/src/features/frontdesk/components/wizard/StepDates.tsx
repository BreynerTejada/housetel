import { addDays } from 'date-fns'
import { UsersRound } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { DateRangePicker } from '@/components/DatePicker'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { formatDate, formatDateRange, nightsBetween, normalizeLang, parseDate, toISODate } from '@/lib/format'
import type { GroupBlock } from '../../api'
import { tr } from '../../lib/labels'
import type { StepErrors, WizardState } from '../../lib/wizard'
import { Counter } from '../Counter'
import { FieldError } from './FieldError'

const AGES = Array.from({ length: 18 }, (_, age) => age)

function plusDays(day: string, days: number): string {
  return toISODate(addDays(parseDate(day) ?? new Date(), days))
}

/**
 * Step 1 — when and who: dates (or nights for a walk-in), adults, children with their ages, promo, IVA, and
 * whether it is a group reservation (a new group, or the existing one the group page opened the wizard for).
 */
export function StepDates({
  state,
  update,
  errors,
  bd,
  groupLabel,
  block,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
  bd: string
  /** Name of the existing group (`?group=`), once loaded. */
  groupLabel?: string
  /** The allotment the rooms are picked up from (`?block=`), once loaded. */
  block?: GroupBlock
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const ids = {
    walkIn: useId(),
    group: useId(),
    groupName: useId(),
    groupError: useId(),
    dates: useId(),
    promo: useId(),
    foreign: useId(),
    datesError: useId(),
    agesError: useId(),
  }
  const nights = Math.max(1, nightsBetween(state.checkin, state.checkout))

  /** New dates or a promo change the offers: the rooms picked are dropped. */
  function change(patch: Partial<WizardState>) {
    update({ ...patch, selection: {}, split: null })
  }

  /** Other guests keep the rooms picked, split again automatically. */
  function changeParty(patch: Partial<WizardState>) {
    update({ ...patch, split: null })
  }

  function setChildren(children: number) {
    const ages = [...state.childrenAges.slice(0, children)]
    while (ages.length < children) ages.push(null)
    changeParty({ children, childrenAges: ages })
  }

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
        <div>
          <Label htmlFor={ids.walkIn} className="font-semibold">
            {t('wizard.walkIn')}
          </Label>
          <p className="text-[13px] text-muted">{t('wizard.walkInHint')}</p>
        </div>
        <Switch
          id={ids.walkIn}
          checked={state.walkIn}
          onCheckedChange={(walkIn) => change(walkIn ? { walkIn, checkin: bd, checkout: plusDays(bd, nights) } : { walkIn })}
        />
      </div>

      {state.groupId ? (
        <div className="flex items-center gap-3 rounded-lg border border-accent/40 bg-accent-soft/40 px-4 py-3">
          <UsersRound aria-hidden className="size-4 shrink-0 text-accent-ink" />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-fg">{t('wizard.group.existing')}</p>
            <p className="truncate text-[13px] text-muted">{groupLabel ?? '…'}</p>
            {state.blockId && (
              <p className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[13px] text-fg">
                {block && <span aria-hidden className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: block.room_type.color }} />}
                <span className="truncate">
                  {block
                    ? t('wizard.group.fromBlock', {
                        units: block.units,
                        type: tr(block.room_type.name, i18n.language),
                        dates: formatDateRange(block.start, block.end, lang),
                      })
                    : t('wizard.group.fromBlockLoading')}
                </span>
              </p>
            )}
          </div>
          <Badge tone="accent" className="ml-auto shrink-0">
            {state.blockId ? t('wizard.group.blockBadge') : t('wizard.group.badge')}
          </Badge>
        </div>
      ) : (
        <div className="grid gap-3 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <Label htmlFor={ids.group} className="font-semibold">
                {t('wizard.group.toggle')}
              </Label>
              <p className="text-[13px] text-muted">{t('wizard.group.hint')}</p>
            </div>
            <Switch id={ids.group} checked={state.groupMode} onCheckedChange={(groupMode) => update({ groupMode })} />
          </div>
          {state.groupMode && (
            <div className="grid gap-1.5">
              <Label htmlFor={ids.groupName} className="text-[13px] font-semibold">
                {t('wizard.group.name')}
              </Label>
              <Input
                id={ids.groupName}
                value={state.groupName}
                onChange={(event) => update({ groupName: event.target.value })}
                placeholder={t('wizard.group.namePlaceholder')}
                maxLength={200}
                aria-invalid={Boolean(errors.group)}
                aria-describedby={errors.group ? ids.groupError : undefined}
                className="bg-surface"
              />
              <FieldError id={ids.groupError} error={errors.group} />
            </div>
          )}
        </div>
      )}

      {state.walkIn ? (
        <div className="grid gap-3">
          <p className="text-[13px] text-muted">
            {t('wizard.arrivesToday', { date: formatDate(bd, lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", lang) })}
          </p>
          <Counter
            label={t('wizard.nights')}
            hint={t('wizard.leaves', { date: formatDate(state.checkout, lang === 'en' ? 'EEE, MMM d' : 'EEE d MMM', lang) })}
            value={nights}
            min={1}
            max={60}
            onChange={(value) => change({ checkin: bd, checkout: plusDays(bd, value) })}
            addLabel={t('wizard.addNight')}
            removeLabel={t('wizard.removeNight')}
          />
        </div>
      ) : (
        <div className="grid gap-2">
          <Label htmlFor={ids.dates} className="font-semibold">
            {t('wizard.dates')}
          </Label>
          <DateRangePicker
            id={ids.dates}
            value={state.checkin && state.checkout ? { from: state.checkin, to: state.checkout } : null}
            onChange={(range) => change({ checkin: range?.from ?? '', checkout: range?.to ?? '' })}
            today={bd}
            min={bd}
            minNights={1}
            showNights
            aria-invalid={Boolean(errors.dates)}
            className="max-w-sm"
          />
        </div>
      )}
      <FieldError id={ids.datesError} error={errors.dates} />

      <div className="grid gap-4 border-t border-border pt-5">
        <Counter
          label={t('wizard.adults')}
          value={state.adults}
          min={1}
          max={60}
          onChange={(adults) => changeParty({ adults })}
          addLabel={t('wizard.addAdult')}
          removeLabel={t('wizard.removeAdult')}
        />
        <FieldError error={errors.adults} />
        <Counter
          label={t('wizard.children')}
          hint={t('wizard.childrenHint')}
          value={state.children}
          min={0}
          max={20}
          onChange={setChildren}
          addLabel={t('wizard.addChild')}
          removeLabel={t('wizard.removeChild')}
        />
        {state.children > 0 && (
          <div className="grid gap-2 sm:grid-cols-3">
            {state.childrenAges.slice(0, state.children).map((age, index) => (
              <Select
                key={index}
                value={age === null ? '' : String(age)}
                onValueChange={(value) => {
                  const ages = [...state.childrenAges]
                  ages[index] = Number(value)
                  changeParty({ childrenAges: ages })
                }}
              >
                <SelectTrigger aria-label={t('wizard.childAge', { number: index + 1 })} aria-invalid={age === null && Boolean(errors.childrenAges)}>
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
        <FieldError id={ids.agesError} error={errors.childrenAges} />
      </div>

      <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor={ids.promo} className="font-semibold">
            {t('wizard.promo')}
          </Label>
          <Input
            id={ids.promo}
            value={state.promoCode}
            onChange={(event) => change({ promoCode: event.target.value })}
            placeholder={t('wizard.promoPlaceholder')}
            autoComplete="off"
            className="uppercase"
          />
        </div>
        <div className="flex items-center justify-between gap-3 self-end rounded-lg border border-border px-3 py-2.5">
          <Label htmlFor={ids.foreign} className="text-[13px] font-semibold">
            {t('wizard.foreign')}
          </Label>
          <Switch id={ids.foreign} checked={state.foreign} onCheckedChange={(foreign) => update({ foreign })} />
        </div>
      </div>
    </div>
  )
}

