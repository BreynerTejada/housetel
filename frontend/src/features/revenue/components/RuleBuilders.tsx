import { Plus, Trash } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { DatePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { normalizeLang } from '@/lib/format'
import { parseNumber, WEEKDAYS, type DraftErrors, type ParamsDraft, type TierDraft, type WindowDraft } from '../lib/rules'
import { Field } from './Field'
import { TierBar } from './RuleVisual'

type Translate = (key: string) => string

function useErrorText() {
  const { t } = useTranslation('revenue')
  return (errors: DraftErrors, key: string) => (errors[key] ? t(errors[key]) : null)
}

const numberInput = 'num text-right'

// ---- Occupancy ------------------------------------------------------------------------------------------

export function OccupancyBuilder({
  value,
  errors,
  onChange,
}: {
  value: ParamsDraft['occupancy']
  errors: DraftErrors
  onChange: (value: ParamsDraft['occupancy']) => void
}) {
  const { t } = useTranslation('revenue')
  const errorText = useErrorText()
  const tiers = value.tiers
  const setTier = (index: number, patch: Partial<TierDraft>) =>
    onChange({ tiers: tiers.map((tier, i) => (i === index ? { ...tier, ...patch } : tier)) })
  const preview = tiers.flatMap((tier) => {
    const [min, max, adjust] = [parseNumber(tier.min), parseNumber(tier.max), parseNumber(tier.adjust)]
    return min !== null && max !== null && adjust !== null && min < max ? [{ min, max, adjust }] : []
  })
  return (
    <fieldset className="grid gap-3">
      <legend className="mb-2 text-[13px] font-semibold text-fg">{t('editor.tiers')}</legend>
      {tiers.map((tier, index) => (
        <div
          key={index}
          role="group"
          aria-label={t('editor.tierLabel', { index: index + 1 })}
          className="grid grid-cols-[repeat(3,minmax(0,1fr))_auto] items-start gap-2"
        >
          <Field label={t('editor.tierFrom')} error={errorText(errors, `tiers.${index}.min`)}>
            {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={tier.min} onChange={(e) => setTier(index, { min: e.target.value })} />}
          </Field>
          <Field label={t('editor.tierTo')} error={errorText(errors, `tiers.${index}.max`)}>
            {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={tier.max} onChange={(e) => setTier(index, { max: e.target.value })} />}
          </Field>
          <Field label={t('editor.adjust')} error={errorText(errors, `tiers.${index}.adjust`)}>
            {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={tier.adjust} onChange={(e) => setTier(index, { adjust: e.target.value })} />}
          </Field>
          <Button
            variant="ghost"
            size="icon-sm"
            className="mt-[26px]"
            aria-label={t('editor.removeTier', { index: index + 1 })}
            onClick={() => onChange({ tiers: tiers.filter((_, i) => i !== index) })}
          >
            <Trash aria-hidden />
          </Button>
        </div>
      ))}
      <div>
        <Button size="sm" onClick={() => onChange({ tiers: [...tiers, { min: '', max: '', adjust: '' }] })}>
          <Plus aria-hidden />
          {t('editor.addTier')}
        </Button>
      </div>
      <TierBar tiers={preview} />
      <p className="text-xs text-muted">{t('editor.tiersHint')}</p>
    </fieldset>
  )
}

// ---- Lead time ------------------------------------------------------------------------------------------

function WindowList({
  title,
  daysLabel,
  prefix,
  windows,
  errors,
  onChange,
}: {
  title: string
  daysLabel: string
  prefix: 'last_minute' | 'early_bird'
  windows: WindowDraft[]
  errors: DraftErrors
  onChange: (windows: WindowDraft[]) => void
}) {
  const { t } = useTranslation('revenue')
  const errorText = useErrorText()
  const setWindow = (index: number, patch: Partial<WindowDraft>) =>
    onChange(windows.map((window, i) => (i === index ? { ...window, ...patch } : window)))
  return (
    <fieldset className="grid gap-3">
      <legend className="mb-2 text-[13px] font-semibold text-fg">{title}</legend>
      {windows.map((window, index) => (
        <div
          key={index}
          role="group"
          aria-label={`${title} · ${t('editor.windowLabel', { index: index + 1 })}`}
          className="grid grid-cols-[repeat(2,minmax(0,1fr))_auto] items-start gap-2"
        >
          <Field label={daysLabel} error={errorText(errors, `${prefix}.${index}.days`)}>
            {(props) => <Input {...props} inputMode="numeric" className={numberInput} value={window.days} onChange={(e) => setWindow(index, { days: e.target.value })} />}
          </Field>
          <Field label={t('editor.adjust')} error={errorText(errors, `${prefix}.${index}.adjust`)}>
            {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={window.adjust} onChange={(e) => setWindow(index, { adjust: e.target.value })} />}
          </Field>
          <Button
            variant="ghost"
            size="icon-sm"
            className="mt-[26px]"
            aria-label={`${title} · ${t('editor.removeWindow', { index: index + 1 })}`}
            onClick={() => onChange(windows.filter((_, i) => i !== index))}
          >
            <Trash aria-hidden />
          </Button>
        </div>
      ))}
      <div>
        <Button size="sm" onClick={() => onChange([...windows, { days: '', adjust: '' }])}>
          <Plus aria-hidden />
          {t('editor.addWindow')}
        </Button>
      </div>
    </fieldset>
  )
}

export function LeadTimeBuilder({
  value,
  errors,
  onChange,
}: {
  value: ParamsDraft['lead_time']
  errors: DraftErrors
  onChange: (value: ParamsDraft['lead_time']) => void
}) {
  const { t } = useTranslation('revenue')
  return (
    <div className="grid gap-5">
      <WindowList
        title={t('editor.lastMinute')}
        daysLabel={t('editor.lastMinuteDays')}
        prefix="last_minute"
        windows={value.last_minute}
        errors={errors}
        onChange={(windows) => onChange({ ...value, last_minute: windows })}
      />
      <WindowList
        title={t('editor.earlyBird')}
        daysLabel={t('editor.earlyBirdDays')}
        prefix="early_bird"
        windows={value.early_bird}
        errors={errors}
        onChange={(windows) => onChange({ ...value, early_bird: windows })}
      />
      <p className="text-xs text-muted">{t('editor.leadHint')}</p>
    </div>
  )
}

// ---- Day of week ----------------------------------------------------------------------------------------

export function DayOfWeekBuilder({
  value,
  errors,
  onChange,
}: {
  value: ParamsDraft['day_of_week']
  errors: DraftErrors
  onChange: (value: ParamsDraft['day_of_week']) => void
}) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const errorText = useErrorText()
  const dayName = (day: string) => {
    const name = (t as Translate)(`weekdays.${day}`)
    return lang === 'es' ? name.toLowerCase() : name
  }
  return (
    <fieldset className="grid gap-2">
      <legend className="sr-only">{t('rules.kinds.day_of_week')}</legend>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
        {WEEKDAYS.map((day) => (
          <Field key={day} label={<span title={dayName(day)}>{t(`weekdays.${day}`).slice(0, 3)}</span>} error={errorText(errors, `days.${day}`)}>
            {(props) => (
              <Input
                {...props}
                aria-label={t('editor.dayAdjust', { day: dayName(day) })}
                inputMode="decimal"
                className={numberInput}
                value={value[day]}
                onChange={(e) => onChange({ ...value, [day]: e.target.value })}
              />
            )}
          </Field>
        ))}
      </div>
      <p className="text-xs text-muted">{t('editor.daysHint')}</p>
    </fieldset>
  )
}

// ---- Holiday --------------------------------------------------------------------------------------------

export function HolidayBuilder({
  value,
  errors,
  onChange,
}: {
  value: ParamsDraft['holiday']
  errors: DraftErrors
  onChange: (value: ParamsDraft['holiday']) => void
}) {
  const { t } = useTranslation('revenue')
  const errorText = useErrorText()
  return (
    <div className="grid gap-4">
      <Field label={t('editor.holidayAdjust')} error={errorText(errors, 'holiday.adjust')} className="max-w-48">
        {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={value.adjust} onChange={(e) => onChange({ ...value, adjust: e.target.value })} />}
      </Field>
      <label className="flex items-start gap-3">
        <Switch className="mt-0.5" checked={value.include_bridges} onCheckedChange={(checked) => onChange({ ...value, include_bridges: checked })} />
        <span>
          <span className="block text-[13px] font-semibold text-fg">{t('editor.includeBridges')}</span>
          <span className="block text-xs text-muted">{t('editor.includeBridgesHint')}</span>
        </span>
      </label>
    </div>
  )
}

// ---- Event ----------------------------------------------------------------------------------------------

export function EventBuilder({
  value,
  errors,
  today,
  onChange,
}: {
  value: ParamsDraft['event']
  errors: DraftErrors
  today: string
  onChange: (value: ParamsDraft['event']) => void
}) {
  const { t } = useTranslation('revenue')
  const errorText = useErrorText()
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label={t('editor.eventName')} error={errorText(errors, 'event.name')} className="sm:col-span-2">
        {(props) => <Input {...props} maxLength={120} value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />}
      </Field>
      <Field label={t('editor.eventStart')} error={errorText(errors, 'event.start')}>
        {(props) => (
          <DatePicker
            id={props.id}
            aria-invalid={props['aria-invalid']}
            value={value.start || null}
            min={today}
            onChange={(start) => onChange({ ...value, start: start ?? '', end: start && value.end < start ? start : value.end })}
          />
        )}
      </Field>
      <Field label={t('editor.eventEnd')} error={errorText(errors, 'event.end')}>
        {(props) => (
          <DatePicker id={props.id} aria-invalid={props['aria-invalid']} value={value.end || null} min={value.start || today} onChange={(end) => onChange({ ...value, end: end ?? '' })} />
        )}
      </Field>
      <Field label={t('editor.adjust')} error={errorText(errors, 'event.adjust')} className="max-w-48">
        {(props) => <Input {...props} inputMode="decimal" className={numberInput} value={value.adjust} onChange={(e) => onChange({ ...value, adjust: e.target.value })} />}
      </Field>
    </div>
  )
}
