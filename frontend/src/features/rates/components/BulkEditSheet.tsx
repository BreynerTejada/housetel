import { useMutation } from '@tanstack/react-query'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { DatePicker } from '@/components/DatePicker'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { postBulk, type BulkResult, type GridRoomType } from '../api'
import {
  bulkFormError,
  buildBulkPayload,
  countNights,
  emptyBulkForm,
  hasBulkChanges,
  type BulkForm,
  type Tristate,
} from '../lib/grid-utils'
import { pick } from '../lib/text'

const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
const WEEKEND = [4, 5]
const WEEKDAYS_ONLY = [6, 0, 1, 2, 3]
const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export interface BulkEditSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  planId: string
  planName: string
  currency: string
  roomTypes: GridRoomType[]
  /** First and last night shown by the grid (inclusive). */
  from: string
  to: string
  /** Categories selected when the panel opens (null = all). */
  preset: string[] | null
  onApplied: (result: BulkResult) => void
}

/** Side panel to change many nights and categories of a base plan at once (`POST grid/bulk/`). */
export function BulkEditSheet(props: BulkEditSheetProps) {
  const { t } = useTranslation('rates')
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent side="right" className="w-[min(30rem,94vw)]">
        <SheetHeader>
          <SheetTitle>{t('bulk.title')}</SheetTitle>
          <SheetDescription>{t('bulk.description', { plan: props.planName })}</SheetDescription>
        </SheetHeader>
        {props.open && <BulkForm {...props} />}
      </SheetContent>
    </Sheet>
  )
}

function BulkForm({ planId, currency, roomTypes, from, to, preset, onApplied, onOpenChange }: BulkEditSheetProps) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const [form, setForm] = useState<BulkForm>(() => ({
    ...emptyBulkForm(),
    roomTypeIds: preset ?? roomTypes.map((roomType) => roomType.id),
    from,
    to,
    weekdays: ALL_DAYS,
  }))
  const update = (patch: Partial<BulkForm>) => setForm((current) => ({ ...current, ...patch }))

  const mutation = useMutation({ mutationFn: postBulk, onSuccess: onApplied })

  const allSelected = form.roomTypeIds.length === roomTypes.length
  const nights = form.from && form.to ? countNights(form.from, form.to, form.weekdays) : 0
  const formError = bulkFormError(form)
  const problem =
    form.roomTypeIds.length === 0
      ? t('bulk.needRoomType')
      : form.weekdays.length === 0
        ? t('bulk.needWeekday')
        : !form.from || !form.to || form.to < form.from
          ? t('bulk.needDates')
          : formError === 'price'
            ? t('bulk.needPrice')
            : formError === 'stay'
              ? t('bulk.needStay')
              : null
  const changes = hasBulkChanges(form)
  const canApply = changes && !problem && !mutation.isPending

  function toggleRoomType(id: string, checked: boolean) {
    const ids = checked ? [...form.roomTypeIds, id] : form.roomTypeIds.filter((item) => item !== id)
    update({ roomTypeIds: roomTypes.map((roomType) => roomType.id).filter((item) => ids.includes(item)) })
  }

  function apply() {
    if (!canApply) return
    mutation.mutate(buildBulkPayload(form, planId))
  }

  return (
    <>
      <SheetBody className="grid content-start gap-6">
        <Section title={t('bulk.roomTypes')}>
          <div className="grid gap-2">
            <CheckRow
              label={t('bulk.allRoomTypes')}
              checked={allSelected ? true : form.roomTypeIds.length > 0 ? 'indeterminate' : false}
              onChange={(checked) => update({ roomTypeIds: checked ? roomTypes.map((roomType) => roomType.id) : [] })}
              strong
            />
            <div className="grid gap-2 border-l border-border pl-3">
              {roomTypes.map((roomType) => (
                <CheckRow
                  key={roomType.id}
                  label={pick(roomType.name, lang)}
                  color={roomType.color}
                  checked={form.roomTypeIds.includes(roomType.id)}
                  onChange={(checked) => toggleRoomType(roomType.id, checked)}
                />
              ))}
            </div>
          </div>
        </Section>

        <Section title={t('bulk.nights')} hint={t('bulk.nightsHint')}>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('bulk.firstNight')}>
              {(id) => <DatePicker id={id} value={form.from} onChange={(value) => update({ from: value ?? '' })} />}
            </Field>
            <Field label={t('bulk.lastNight')}>
              {(id) => <DatePicker id={id} value={form.to} min={form.from} onChange={(value) => update({ to: value ?? '' })} />}
            </Field>
          </div>
          <div className="grid gap-2">
            <div className="flex flex-wrap gap-1.5">
              <Button size="sm" variant="subtle" onClick={() => update({ weekdays: ALL_DAYS })}>
                {t('bulk.everyDay')}
              </Button>
              <Button size="sm" variant="subtle" onClick={() => update({ weekdays: WEEKEND })}>
                {t('bulk.weekend')}
              </Button>
              <Button size="sm" variant="subtle" onClick={() => update({ weekdays: WEEKDAYS_ONLY })}>
                {t('bulk.weekdays')}
              </Button>
            </div>
            <ToggleGroup
              type="multiple"
              value={form.weekdays.map(String)}
              onValueChange={(values) => update({ weekdays: values.map(Number).sort((a, b) => a - b) })}
              aria-label={t('bulk.daysOfWeek')}
              className="w-fit"
            >
              {DAY_KEYS.map((key, index) => (
                <ToggleGroupItem
                  key={key}
                  value={String(index)}
                  aria-label={t(`days.${key}`)}
                  className="w-9 px-0 data-[state=on]:bg-accent-soft data-[state=on]:text-accent-ink data-[state=on]:shadow-none"
                >
                  {t(`daysShort.${key}`)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        </Section>

        <Section title={t('bulk.price')}>
          <Choice
            label={t('bulk.price')}
            value={form.price.mode}
            onChange={(mode) => update({ price: { mode, value: '' } })}
            options={[
              { value: 'keep', label: t('bulk.keep'), aria: t('bulk.keepPrice') },
              { value: 'set', label: t('bulk.set'), aria: t('bulk.setPrice') },
              { value: 'percent', label: '± %', aria: t('bulk.percent') },
              { value: 'amount', label: '± $', aria: t('bulk.amount') },
            ]}
          />
          {form.price.mode === 'set' && (
            <MoneyInput
              aria-label={t('bulk.priceValue')}
              currency={currency}
              value={form.price.value}
              onChange={(value) => update({ price: { mode: 'set', value } })}
              className="w-48"
            />
          )}
          {(form.price.mode === 'percent' || form.price.mode === 'amount') && (
            <div className="flex items-center gap-2">
              <Input
                aria-label={t(form.price.mode === 'percent' ? 'bulk.percentValue' : 'bulk.amountValue')}
                inputMode="decimal"
                autoComplete="off"
                value={form.price.value}
                onChange={(event) => update({ price: { mode: form.price.mode, value: event.target.value } })}
                className="num w-32 text-right"
              />
              <span className="text-sm text-muted">{form.price.mode === 'percent' ? '%' : currency}</span>
              <span className="text-xs text-muted">{t('bulk.signedHint')}</span>
            </div>
          )}
        </Section>

        <Section title={t('bulk.stay')}>
          <LosChoice
            label={t('grid.rows.minLos')}
            setLabel={t('bulk.setMinLos')}
            valueLabel={t('bulk.minLosValue')}
            change={form.minLos}
            onChange={(minLos) => update({ minLos })}
          />
          <LosChoice
            label={t('bulk.maxLos')}
            setLabel={t('bulk.setMaxLos')}
            valueLabel={t('bulk.maxLosValue')}
            change={form.maxLos}
            onChange={(maxLos) => update({ maxLos })}
          />
        </Section>

        <Section title={t('bulk.restrictions')}>
          <TristateRow label={t('grid.rows.cta')} value={form.cta} onChange={(cta) => update({ cta })} />
          <TristateRow label={t('grid.rows.ctd')} value={form.ctd} onChange={(ctd) => update({ ctd })} />
          <TristateRow label={t('grid.rows.stopSell')} value={form.stopSell} onChange={(stopSell) => update({ stopSell })} />
        </Section>
      </SheetBody>

      <SheetFooter className="flex-col items-stretch gap-3 sm:flex-col sm:items-stretch">
        {mutation.isError && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {errorMessage(mutation.error, t)}
          </p>
        )}
        <p className="text-[13px] text-muted" aria-live="polite">
          {problem ??
            t('bulk.summary', {
              nights: t('bulk.nightsCount', { count: nights }),
              roomTypes: t('bulk.roomTypesCount', { count: form.roomTypeIds.length }),
            })}
        </p>
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            {t('actions.cancel', { ns: 'common' })}
          </Button>
          <Button variant="primary" onClick={apply} disabled={!canApply} loading={mutation.isPending}>
            {t('bulk.apply')}
          </Button>
        </div>
      </SheetFooter>
    </>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <div>
        <h3 className="eyebrow">{title}</h3>
        {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
    </div>
  )
}

function CheckRow({
  label,
  checked,
  onChange,
  color,
  strong = false,
}: {
  label: string
  checked: boolean | 'indeterminate'
  onChange: (checked: boolean) => void
  color?: string
  strong?: boolean
}) {
  const id = useId()
  return (
    <div className="flex items-center gap-2.5">
      <Checkbox id={id} checked={checked} onCheckedChange={(value) => onChange(value === true)} />
      {color && <span aria-hidden className="h-3.5 w-1 rounded-full" style={{ background: color }} />}
      <label htmlFor={id} className={strong ? 'text-sm font-semibold text-fg' : 'text-sm text-fg'}>
        {label}
      </label>
    </div>
  )
}

interface ChoiceOption<T extends string> {
  value: T
  label: string
  aria?: string
}

function Choice<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: T
  onChange: (value: T) => void
  options: ChoiceOption<T>[]
}) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(next) => next && onChange(next as T)}
      aria-label={label}
      className="w-fit"
    >
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value} aria-label={option.aria}>
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

function LosChoice({
  label,
  setLabel,
  valueLabel,
  change,
  onChange,
}: {
  label: string
  setLabel: string
  valueLabel: string
  change: BulkForm['minLos']
  onChange: (change: BulkForm['minLos']) => void
}) {
  const { t } = useTranslation('rates')
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="w-28 text-[13px] font-semibold text-fg">{label}</span>
      <Choice
        label={label}
        value={change.mode}
        onChange={(mode) => onChange({ mode, value: '' })}
        options={[
          { value: 'keep', label: t('bulk.keep') },
          { value: 'set', label: t('bulk.set'), aria: setLabel },
          { value: 'clear', label: t('bulk.clear') },
        ]}
      />
      {change.mode === 'set' && (
        <Input
          aria-label={valueLabel}
          inputMode="numeric"
          autoComplete="off"
          value={change.value}
          onChange={(event) => onChange({ mode: 'set', value: event.target.value })}
          className="num w-20 text-right"
        />
      )}
    </div>
  )
}

function TristateRow({ label, value, onChange }: { label: string; value: Tristate; onChange: (value: Tristate) => void }) {
  const { t } = useTranslation('rates')
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-[13px] font-semibold text-fg">{label}</span>
      <Choice
        label={label}
        value={value}
        onChange={onChange}
        options={[
          { value: 'keep', label: t('bulk.keep') },
          { value: 'on', label: t('bulk.close') },
          { value: 'off', label: t('bulk.open') },
        ]}
      />
    </div>
  )
}
