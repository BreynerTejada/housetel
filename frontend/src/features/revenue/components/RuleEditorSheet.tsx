import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useSaveRule, useSimulate, type Combine, type PricingRule, type RevenueOptions, type RuleKind, type SimulateResult } from '../api'
import { compactMoney, pick, signedPercent } from '../lib/format'
import { draftFromRule, draftToInput, newRuleDraft, RULE_KINDS, type DraftErrors, type RuleDraft } from '../lib/rules'
import { Field } from './Field'
import { KindIcon } from './KindIcon'
import { DayOfWeekBuilder, EventBuilder, HolidayBuilder, LeadTimeBuilder, OccupancyBuilder } from './RuleBuilders'

/** API fields the form shows next to a control. */
const SHOWN_FIELDS = ['name', 'params', 'room_types', 'priority']

export interface RuleEditorSheetProps {
  /** `undefined` = closed, `null` = new rule. */
  rule: PricingRule | null | undefined
  options: RevenueOptions | undefined
  today: string
  onClose: () => void
}

/** Create or edit a rule with the visual builder of its kind, and try it on today's data before saving. */
export function RuleEditorSheet({ rule, options, today, onClose }: RuleEditorSheetProps) {
  const { t } = useTranslation('revenue')
  const open = rule !== undefined
  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="right" className="w-[min(40rem,100vw)]">
        <SheetHeader>
          <SheetTitle>{rule ? t('editor.editTitle') : t('editor.newTitle')}</SheetTitle>
          <SheetDescription>{t('editor.description')}</SheetDescription>
        </SheetHeader>
        {open && <RuleEditorForm key={rule?.id ?? 'new'} rule={rule} options={options} today={today} onClose={onClose} />}
      </SheetContent>
    </Sheet>
  )
}

function RuleEditorForm({ rule, options, today, onClose }: { rule: PricingRule | null; options: RevenueOptions | undefined; today: string; onClose: () => void }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const [draft, setDraft] = useState<RuleDraft>(() => (rule ? draftFromRule(rule, today) : newRuleDraft('occupancy', today)))
  const [errors, setErrors] = useState<DraftErrors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [preview, setPreview] = useState<SimulateResult | null>(null)
  const save = useSaveRule()
  const simulate = useSimulate()

  function update(patch: Partial<RuleDraft>) {
    setDraft((current) => ({ ...current, ...patch }))
    setPreview(null)
  }

  function updateParams<K extends keyof RuleDraft['params']>(kind: K, value: RuleDraft['params'][K]) {
    setDraft((current) => ({ ...current, params: { ...current.params, [kind]: value } }))
    setPreview(null)
  }

  function validated() {
    const result = draftToInput(draft)
    setErrors(result.errors)
    setServerError(null)
    return result.input
  }

  function submit() {
    const input = validated()
    if (!input) return
    save.mutate(
      { id: rule?.id, body: input },
      {
        onSuccess: () => {
          toast.success(t('rules.saved'))
          onClose()
        },
        onError: (error) => {
          // Field errors go next to their field; anything the form cannot place is shown at the bottom.
          const fields = isApiError(error) ? Object.entries(error.fields ?? {}) : []
          const fieldErrors: DraftErrors = {}
          for (const [field, messages] of fields) fieldErrors[`server.${field}`] = messages[0] ?? ''
          setErrors(fieldErrors)
          const placed = fields.length > 0 && fields.every(([field]) => SHOWN_FIELDS.includes(field))
          setServerError(placed ? null : errorMessage(error, t))
        },
      },
    )
  }

  function tryIt() {
    const input = validated()
    if (!input) return
    simulate.mutate(
      { rule: rule ? { ...input, id: rule.id } : input },
      { onSuccess: setPreview, onError: (error) => setServerError(errorMessage(error, t)) },
    )
  }

  const errorText = (key: string) => (errors[key] ? t(errors[key]) : (errors[`server.${key}`] ?? null))
  const paramsError = errorText('params')

  return (
    <>
      <SheetBody className="grid content-start gap-6">
        <Field label={t('editor.name')} error={errorText('name')}>
          {(props) => (
            <Input {...props} value={draft.name} placeholder={t('editor.namePlaceholder')} maxLength={120} onChange={(e) => update({ name: e.target.value })} />
          )}
        </Field>

        {!rule && (
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-[13px] font-semibold text-fg">{t('editor.kind')}</legend>
            <RadioGroup value={draft.kind} onValueChange={(kind) => update({ kind: kind as RuleKind })} className="grid gap-2 sm:grid-cols-2">
              {RULE_KINDS.map((kind) => (
                <label
                  key={kind}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:border-border-strong',
                    draft.kind === kind && 'border-accent bg-accent-soft/40',
                  )}
                >
                  <RadioGroupItem value={kind} className="mt-0.5" aria-describedby={`kind-hint-${kind}`} />
                  <KindIcon kind={kind} className="mt-0.5 size-4 shrink-0 text-muted" />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-semibold text-fg">{t(`rules.kinds.${kind}`)}</span>
                    <span id={`kind-hint-${kind}`} className="block text-xs text-muted">
                      {t(`rules.kindHints.${kind}`)}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          </fieldset>
        )}

        <section aria-label={t(`rules.kinds.${draft.kind}`)} className="grid gap-3 rounded-lg border border-border bg-surface-2/40 p-4">
          {rule && (
            <p className="flex items-center gap-2 text-[13px] font-semibold text-fg">
              <KindIcon kind={draft.kind} className="size-4 text-muted" />
              {t(`rules.kinds.${draft.kind}`)}
            </p>
          )}
          {draft.kind === 'occupancy' && (
            <OccupancyBuilder value={draft.params.occupancy} errors={errors} onChange={(value) => updateParams('occupancy', value)} />
          )}
          {draft.kind === 'lead_time' && (
            <LeadTimeBuilder value={draft.params.lead_time} errors={errors} onChange={(value) => updateParams('lead_time', value)} />
          )}
          {draft.kind === 'day_of_week' && (
            <DayOfWeekBuilder value={draft.params.day_of_week} errors={errors} onChange={(value) => updateParams('day_of_week', value)} />
          )}
          {draft.kind === 'holiday' && (
            <HolidayBuilder value={draft.params.holiday} errors={errors} onChange={(value) => updateParams('holiday', value)} />
          )}
          {draft.kind === 'event' && (
            <EventBuilder value={draft.params.event} errors={errors} today={today} onChange={(value) => updateParams('event', value)} />
          )}
          {paramsError && (
            <p role="alert" className="text-xs font-medium text-danger-ink">
              {paramsError}
            </p>
          )}
        </section>

        <fieldset className="grid gap-2">
          <legend className="mb-2 text-[13px] font-semibold text-fg">{t('editor.roomTypes')}</legend>
          <label className="flex items-center gap-2 text-[13px] font-semibold text-fg">
            <Switch checked={draft.allRoomTypes} onCheckedChange={(checked) => update({ allRoomTypes: checked })} />
            {t('editor.allRoomTypes')}
          </label>
          {!draft.allRoomTypes && (
            <div className="grid gap-2 pl-1 sm:grid-cols-2">
              {(options?.room_types ?? []).map((roomType) => (
                <label key={roomType.id} className="flex items-center gap-2 text-[13px] text-fg">
                  <Checkbox
                    checked={draft.room_types.includes(roomType.id)}
                    onCheckedChange={(checked) =>
                      update({
                        room_types: checked ? [...draft.room_types, roomType.id] : draft.room_types.filter((id) => id !== roomType.id),
                      })
                    }
                  />
                  <span aria-hidden className="h-3.5 w-1 rounded-full" style={{ background: roomType.color }} />
                  {pick(roomType.name, lang)}
                </label>
              ))}
            </div>
          )}
          {errorText('room_types') && <p className="text-xs font-medium text-danger-ink">{errorText('room_types')}</p>}
        </fieldset>

        <fieldset className="grid gap-2">
          <legend className="mb-2 text-[13px] font-semibold text-fg">{t('editor.combine')}</legend>
          <RadioGroup value={draft.combine} onValueChange={(combine) => update({ combine: combine as Combine })} className="grid gap-2 sm:grid-cols-2">
            {(['stack', 'max'] as const).map((combine) => (
              <label
                key={combine}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:border-border-strong',
                  draft.combine === combine && 'border-accent bg-accent-soft/40',
                )}
              >
                <RadioGroupItem value={combine} className="mt-0.5" aria-describedby={`combine-hint-${combine}`} />
                <span>
                  <span className="block text-[13px] font-semibold text-fg">
                    {t(combine === 'stack' ? 'editor.combineStack' : 'editor.combineMax')}
                  </span>
                  <span id={`combine-hint-${combine}`} className="block text-xs text-muted">
                    {t(combine === 'stack' ? 'editor.combineStackHint' : 'editor.combineMaxHint')}
                  </span>
                </span>
              </label>
            ))}
          </RadioGroup>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('editor.priority')} hint={t('editor.priorityHint')} error={errorText('priority')}>
            {(props) => <Input {...props} inputMode="numeric" className="num" value={draft.priority} onChange={(e) => update({ priority: e.target.value })} />}
          </Field>
          <label className="flex items-center gap-2 self-start pt-7 text-[13px] font-semibold text-fg">
            <Switch checked={draft.is_active} onCheckedChange={(checked) => update({ is_active: checked })} />
            {t('editor.active')}
          </label>
        </div>

        <section aria-label={t('editor.preview')} className="grid gap-2 rounded-lg border border-dashed border-border-strong p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted">{t('editor.previewHint')}</p>
            <Button size="sm" onClick={tryIt} loading={simulate.isPending}>
              <FlaskConical aria-hidden />
              {t('editor.preview')}
            </Button>
          </div>
          {preview && (
            <p aria-live="polite" className="text-[13px] text-fg">
              {preview.summary.count === 0
                ? t('editor.previewNone')
                : t('editor.previewResult', {
                    count: preview.summary.count,
                    upDown: `${t('kpis.up', { count: preview.summary.up })} · ${t('kpis.down', { count: preview.summary.down })}`,
                    avg: signedPercent(preview.summary.avg_change_percent, lang),
                    impact: compactMoney(preview.summary.estimated_impact, lang),
                  })}
            </p>
          )}
        </section>

        {serverError && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {serverError}
          </p>
        )}
        {Object.keys(errors).length > 0 && !serverError && (
          <p role="alert" className="text-sm font-medium text-danger-ink">
            {t('editor.fix')}
          </p>
        )}
      </SheetBody>
      <SheetFooter>
        <Button onClick={onClose} disabled={save.isPending}>
          {t('common:actions.cancel')}
        </Button>
        <Button variant="primary" onClick={submit} loading={save.isPending}>
          {rule ? t('editor.save') : t('editor.create')}
        </Button>
      </SheetFooter>
    </>
  )
}
