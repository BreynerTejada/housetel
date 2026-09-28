import type { TFunction } from 'i18next'
import { ArrowLeft, ArrowRight, CalendarDays, TriangleAlert } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { formatNumber, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  DATE_FORMATS,
  useConfigureImport,
  type DateFormat,
  type JobDetail,
  type JobOptions,
  type OnExisting,
  type RatePlanOption,
  type RoomTypeOption,
  type ValueCandidate,
  type ValueMap,
} from '../api'

const NONE = '__none__'
const AUTO = '__auto__'
const DATE_FIELDS = ['checkin', 'checkout', 'birth_date', 'booked_at']

function name(option: { code: string; name: { es: string; en: string } }, lang: Lang): string {
  return option.name[lang] || option.name.es || option.code
}

/** Initial choices: what was saved, else the automatic match of each value. */
function initialValues(job: JobDetail): Required<ValueMap> {
  const pick = (key: 'room_type' | 'rate_plan') =>
    Object.fromEntries((job.values[key] ?? []).map((item) => [item.value, item.selected ?? '']))
  return { room_type: pick('room_type'), rate_plan: pick('rate_plan') }
}

/**
 * Step 3b: which Housetel category (and rate plan) each value of the file is — "Standard", "Doble vista mar"… —
 * and how to read the file: dates, taxes in the amounts, what to do with records imported before, and the
 * name of the previous system (it namespaces the ids, so importing again updates instead of duplicating).
 */
export function MapValuesView({ job, onBack, onNext }: { job: JobDetail; onBack: () => void; onNext: () => void }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const configure = useConfigureImport(job.id)
  const [values, setValues] = useState<Required<ValueMap>>(() => initialValues(job))
  const [options, setOptions] = useState<JobOptions>(() => ({ ...job.options }))
  const [sourceLabel, setSourceLabel] = useState(job.source_label)
  const sourceId = useId()
  const isReservations = job.kind === 'reservations'
  const roomTypeValues = job.values.room_type ?? []
  const planValues = job.values.rate_plan ?? []
  const hasDates = DATE_FIELDS.some((code) => job.mapping[code])
  const unassigned =
    roomTypeValues.filter((item) => !values.room_type[item.value]).length +
    planValues.filter((item) => !values.rate_plan[item.value]).length

  function patch(next: Partial<JobOptions>) {
    setOptions((current) => ({ ...current, ...next }))
  }

  function save() {
    configure.mutate(
      {
        value_map: values,
        options: {
          date_format: options.date_format,
          amounts_include_tax: options.amounts_include_tax,
          on_existing: options.on_existing,
          default_rate_plan: options.default_rate_plan,
        },
        ...(sourceLabel.trim() && sourceLabel.trim() !== job.source_label ? { source_label: sourceLabel.trim() } : {}),
      },
      { onSuccess: onNext },
    )
  }

  const basePlan = job.rate_plans.find((plan) => plan.kind === 'base') ?? job.rate_plans[0]

  return (
    <div className="grid gap-5">
      {roomTypeValues.length > 0 && (
        <ValueSection
          title={t('values.roomTypes')}
          hint={t('values.roomTypesHint')}
          items={roomTypeValues}
          chosen={values.room_type}
          lang={lang}
          options={job.room_types.filter((item) => item.is_active)}
          describe={(option) => describeRoomType(option, lang, t)}
          onChange={(value, target) => setValues((current) => ({ ...current, room_type: { ...current.room_type, [value]: target } }))}
        />
      )}
      {isReservations && planValues.length > 0 && (
        <ValueSection
          title={t('values.ratePlans')}
          hint={t('values.ratePlansHint')}
          items={planValues}
          chosen={values.rate_plan}
          lang={lang}
          options={job.rate_plans}
          describe={(option) => `${option.code} · ${name(option, lang)}`}
          onChange={(value, target) => setValues((current) => ({ ...current, rate_plan: { ...current.rate_plan, [value]: target } }))}
        />
      )}

      <section aria-labelledby="values-options" className="rounded-xl border border-border bg-surface shadow-xs">
        <h2 id="values-options" className="border-b border-border px-4 py-3 text-sm font-bold tracking-[-0.01em] sm:px-5">
          {t('options.title')}
        </h2>
        <div className="grid divide-y divide-border">
          {isReservations && (
            <OptionRow label={t('options.defaultPlan')} hint={t('options.defaultPlanHint')}>
              <Select
                value={options.default_rate_plan || AUTO}
                onValueChange={(value) => patch({ default_rate_plan: value === AUTO ? '' : value })}
              >
                <SelectTrigger aria-label={t('options.defaultPlan')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO}>
                    {basePlan ? t('options.defaultPlanAuto', { plan: name(basePlan, lang) }) : t('options.defaultPlanNone')}
                  </SelectItem>
                  {job.rate_plans.map((plan: RatePlanOption) => (
                    <SelectItem key={plan.id} value={plan.id}>
                      {plan.code} · {name(plan, lang)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </OptionRow>
          )}

          {hasDates && (
            <OptionRow label={t('options.dateFormat')} hint={t('options.dateFormatHint')}>
              <Select value={options.date_format} onValueChange={(value) => patch({ date_format: value as DateFormat })}>
                <SelectTrigger aria-label={t('options.dateFormat')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DATE_FORMATS.map((format) => (
                    <SelectItem key={format} value={format}>
                      {format === 'auto' && job.options.date_format_detected
                        ? t('options.dateAutoDetected', { format: t(`options.dateFormats.${job.options.date_format_detected}`) })
                        : t(`options.dateFormats.${format}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {options.date_format === 'auto' && job.options.date_format_ambiguous && (
                <p className="flex gap-1.5 text-xs leading-4 text-warning-ink">
                  <CalendarDays aria-hidden className="mt-px size-3.5 shrink-0" />
                  {t('options.dateAmbiguous')}
                </p>
              )}
            </OptionRow>
          )}

          {isReservations && (
            <OptionRow label={t('options.includesTax')} hint={t('options.includesTaxHint')} inline>
              <Switch
                checked={options.amounts_include_tax}
                onCheckedChange={(checked) => patch({ amounts_include_tax: checked })}
                aria-label={t('options.includesTax')}
              />
            </OptionRow>
          )}

          <OptionRow label={t('options.onExisting')} hint={t('options.onExistingHint', { source: sourceLabel || job.source_label })}>
            <RadioGroup
              value={options.on_existing}
              onValueChange={(value) => patch({ on_existing: value as OnExisting })}
              aria-label={t('options.onExisting')}
              className="gap-2"
            >
              {(['update', 'skip'] as const).map((value) => (
                <label key={value} className="flex items-start gap-2.5 text-sm">
                  <RadioGroupItem value={value} className="mt-0.5" />
                  <span>
                    <span className="block font-semibold text-fg">{t(`options.existing.${value}`)}</span>
                    <span className="block text-xs text-muted">{t(`options.existing.${value}Hint`)}</span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          </OptionRow>

          <OptionRow label={t('options.source')} hint={t('options.sourceHint')} htmlFor={sourceId}>
            <Input id={sourceId} value={sourceLabel} maxLength={100} onChange={(event) => setSourceLabel(event.target.value)} />
          </OptionRow>
        </div>
      </section>

      {unassigned > 0 && (
        <p role="status" className="flex gap-2 rounded-lg bg-warning-soft px-4 py-3 text-[13px] text-warning-ink">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('values.unassigned', { count: unassigned })}
        </p>
      )}
      {configure.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(configure.error, t)}
        </p>
      )}

      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-between gap-3 border-t border-border bg-bg/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
        <Button variant="ghost" onClick={onBack} disabled={configure.isPending}>
          <ArrowLeft aria-hidden />
          {t('values.back')}
        </Button>
        <Button variant="primary" onClick={save} loading={configure.isPending}>
          {t('values.next')}
          <ArrowRight aria-hidden />
        </Button>
      </div>
    </div>
  )
}

function describeRoomType(option: RoomTypeOption, lang: Lang, t: TFunction): string {
  const capacity =
    option.kind === 'dorm' ? t('values.dorm') : t('values.capacity', { adults: option.max_adults, total: option.max_occupancy })
  return `${option.code} · ${name(option, lang)} (${capacity})`
}

function ValueSection<O extends { id: string; code: string; name: { es: string; en: string } }>({
  title,
  hint,
  items,
  chosen,
  options,
  lang,
  describe,
  onChange,
}: {
  title: string
  hint: string
  items: ValueCandidate[]
  chosen: Record<string, string>
  options: O[]
  lang: Lang
  describe: (option: O) => string
  onChange: (value: string, target: string) => void
}) {
  const { t } = useTranslation('imports')
  return (
    <section className="rounded-xl border border-border bg-surface shadow-xs">
      <div className="border-b border-border px-4 py-3 sm:px-5">
        <h2 className="text-sm font-bold tracking-[-0.01em]">{title}</h2>
        <p className="mt-0.5 text-xs leading-4 text-muted">{hint}</p>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item) => {
          const target = chosen[item.value] ?? ''
          const auto = Boolean(item.suggested) && target === item.suggested
          return (
            <li key={item.value} className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,17rem)] sm:items-center sm:gap-5 sm:px-5">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="max-w-full truncate rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-[13px] font-semibold text-fg">
                  {item.value}
                </span>
                <span className="num text-xs text-muted">{t('values.rows', { count: item.count, formatted: formatNumber(item.count, lang, 0) })}</span>
                {auto && <span className="text-xs font-medium text-accent-ink">{t('values.auto')}</span>}
              </div>
              <Select value={target || NONE} onValueChange={(value) => onChange(item.value, value === NONE ? '' : value)}>
                <SelectTrigger aria-label={t('values.mapTo', { value: item.value })} aria-invalid={!target || undefined} className={cn(!target && 'text-warning-ink')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>{t('values.none')}</SelectItem>
                  {options.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {describe(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function OptionRow({
  label,
  hint,
  children,
  inline = false,
  htmlFor,
}: {
  label: string
  hint?: string
  children: ReactNode
  inline?: boolean
  htmlFor?: string
}) {
  return (
    <div
      className={cn(
        'grid gap-2 px-4 py-3 sm:px-5',
        inline ? 'grid-cols-[minmax(0,1fr)_auto] items-center gap-4' : 'sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] sm:gap-5',
      )}
    >
      <div className="min-w-0">
        {htmlFor ? (
          <Label htmlFor={htmlFor} className="font-semibold text-fg">
            {label}
          </Label>
        ) : (
          <p className="font-semibold text-fg">{label}</p>
        )}
        {hint && <p className="mt-0.5 text-xs leading-4 text-muted">{hint}</p>}
      </div>
      <div className="grid min-w-0 gap-1.5">{children}</div>
    </div>
  )
}
