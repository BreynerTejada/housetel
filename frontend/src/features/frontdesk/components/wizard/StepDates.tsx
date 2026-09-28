import { addDays } from 'date-fns'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { DateRangePicker } from '@/components/DatePicker'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { formatDate, nightsBetween, normalizeLang, parseDate, toISODate } from '@/lib/format'
import type { StepErrors, WizardState } from '../../lib/wizard'
import { Counter } from '../Counter'
import { FieldError } from './FieldError'

const AGES = Array.from({ length: 18 }, (_, age) => age)

function plusDays(day: string, days: number): string {
  return toISODate(addDays(parseDate(day) ?? new Date(), days))
}

/** Step 1 — when and who: dates (or nights for a walk-in), adults, children with their ages, promo, IVA. */
export function StepDates({
  state,
  update,
  errors,
  bd,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
  bd: string
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const ids = { walkIn: useId(), dates: useId(), promo: useId(), foreign: useId(), datesError: useId(), agesError: useId() }
  const nights = Math.max(1, nightsBetween(state.checkin, state.checkout))

  /** Anything that changes the price invalidates the chosen offer. */
  function change(patch: Partial<WizardState>) {
    update({ ...patch, offer: null })
  }

  function setChildren(children: number) {
    const ages = [...state.childrenAges.slice(0, children)]
    while (ages.length < children) ages.push(null)
    change({ children, childrenAges: ages })
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
          max={20}
          onChange={(adults) => change({ adults })}
          addLabel={t('wizard.addAdult')}
          removeLabel={t('wizard.removeAdult')}
        />
        <FieldError error={errors.adults} />
        <Counter
          label={t('wizard.children')}
          hint={t('wizard.childrenHint')}
          value={state.children}
          min={0}
          max={10}
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
                  change({ childrenAges: ages })
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
          <Switch id={ids.foreign} checked={state.foreign} onCheckedChange={(foreign) => change({ foreign })} />
        </div>
      </div>
    </div>
  )
}

