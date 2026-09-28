import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, TriangleAlert } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useId, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  messagingKeys,
  updateRule,
  useRules,
  useTemplates,
  type LifecycleRule,
  type LifecycleRuleInput,
  type SendChannel,
} from '../../api'
import { templateOptions, type TemplateOption } from '../../lib/templates'

const CHANNELS: SendChannel[] = ['email', 'whatsapp']
const MAX_OFFSET = 60

/** Where a message sits in the guest's journey (days around the stay; the booking comes first). */
function position(rule: LifecycleRule): number {
  switch (rule.event) {
    case 'confirmation':
      return -1000
    case 'payment_reminder':
      return -rule.days_offset - 0.5
    case 'pre_arrival':
      return -rule.days_offset
    case 'arrival_day':
      return 0
    case 'post_stay':
      return 1000 + rule.days_offset
    default:
      return 2000
  }
}

function useRuleMutation() {
  const { t } = useTranslation('messaging')
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: LifecycleRuleInput }) => updateRule(id, input),
    onMutate: async ({ id, input }) => {
      await queryClient.cancelQueries({ queryKey: messagingKeys.rules })
      const previous = queryClient.getQueryData<LifecycleRule[]>(messagingKeys.rules)
      queryClient.setQueryData<LifecycleRule[]>(messagingKeys.rules, (rules) => rules?.map((rule) => (rule.id === id ? { ...rule, ...input } : rule)))
      return { previous }
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(messagingKeys.rules, context.previous)
      toast.error(errorMessage(error, t))
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<LifecycleRule[]>(messagingKeys.rules, (rules) => rules?.map((rule) => (rule.id === saved.id ? saved : rule)))
      toast.success(t('settings.rules.saved'))
    },
  })
}

/**
 * Tab "Automatic messages": the guest's journey drawn as a line, from the booking to the days after the stay,
 * with each automatic message where it goes out. The stretch of the stay is the warm segment of the line;
 * the cancellation message hangs apart because it only happens if the booking is cancelled.
 */
export function LifecycleRules({ canEdit }: { canEdit: boolean }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const rules = useRules()
  const templates = useTemplates()
  const mutation = useRuleMutation()

  if (rules.isPending) return <LoadingState variant="rows" rows={6} />
  if (rules.isError) return <ErrorState error={rules.error} onRetry={() => rules.refetch()} />

  const options = templateOptions(templates.data, lang)
  const journey = rules.data.filter((rule) => rule.event !== 'cancellation').sort((a, b) => position(a) - position(b))
  const cancellation = rules.data.find((rule) => rule.event === 'cancellation')
  const save = (rule: LifecycleRule, input: LifecycleRuleInput) => mutation.mutate({ id: rule.id, input })

  return (
    <div className="grid max-w-4xl gap-6">
      <p className="max-w-2xl text-[13.5px] text-muted">{t('settings.rules.intro')}</p>
      <ol aria-label={t('settings.rules.journey')} className="grid">
        {journey.map((rule, index) => {
          const previous = journey[index - 1]
          const next = journey[index + 1]
          return (
            <Stop
              key={rule.id}
              rule={rule}
              first={index === 0}
              last={index === journey.length - 1}
              // The stay: from the arrival-day message to the first message after departure.
              stayAbove={previous?.event === 'arrival_day' && rule.event === 'post_stay'}
              stayBelow={rule.event === 'arrival_day' && next?.event === 'post_stay'}
            >
              <RuleCard rule={rule} options={options} canEdit={canEdit} onSave={(input) => save(rule, input)} />
            </Stop>
          )
        })}
      </ol>
      {cancellation && (
        <section aria-labelledby="rules-cancelled" className="grid gap-3">
          <h3 id="rules-cancelled" className="eyebrow">
            {t('settings.rules.cancelledBranch')}
          </h3>
          <ol className="grid">
            <Stop rule={cancellation} first last dashed>
              <RuleCard rule={cancellation} options={options} canEdit={canEdit} onSave={(input) => save(cancellation, input)} />
            </Stop>
          </ol>
        </section>
      )}
    </div>
  )
}

function markerText(rule: LifecycleRule, t: TFunction): string {
  if (rule.uses_offset) return t(`settings.rules.markers.${rule.event}`, { count: rule.days_offset })
  return t(`settings.rules.markers.${rule.event}`)
}

function Stop({
  rule,
  first,
  last,
  stayAbove = false,
  stayBelow = false,
  dashed = false,
  children,
}: {
  rule: LifecycleRule
  first: boolean
  last: boolean
  stayAbove?: boolean
  stayBelow?: boolean
  dashed?: boolean
  children: ReactNode
}) {
  const { t } = useTranslation('messaging')
  const marker = markerText(rule, t)
  const rail = (stay: boolean) => cn('absolute left-1/2 -translate-x-1/2', stay ? 'w-[3px] rounded-full bg-accent/45' : dashed ? 'w-0 border-l border-dashed border-border-strong' : 'w-px bg-border-strong')
  return (
    <li className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[7.5rem_1.25rem_minmax(0,1fr)] sm:gap-x-4">
      <p
        aria-hidden
        className={cn(
          'num hidden pt-[1.15rem] text-right text-[12px] leading-4 font-semibold sm:block',
          rule.event === 'arrival_day' ? 'text-accent-ink' : 'text-muted',
          !rule.enabled && 'text-subtle line-through decoration-1',
        )}
      >
        {marker}
      </p>
      <div aria-hidden className="relative">
        {!first && <span className={cn(rail(stayAbove), 'top-0 h-[1.6rem]')} />}
        <span
          className={cn(
            'absolute top-[1.6rem] left-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition-colors',
            rule.enabled ? 'border-accent bg-accent' : 'border-border-strong bg-bg',
          )}
        />
        {!last && <span className={cn(rail(stayBelow), 'top-[1.6rem] bottom-0')} />}
      </div>
      <div className="min-w-0 pb-4">{children}</div>
    </li>
  )
}

function RuleCard({
  rule,
  options,
  canEdit,
  onSave,
}: {
  rule: LifecycleRule
  options: TemplateOption[]
  canEdit: boolean
  onSave: (input: LifecycleRuleInput) => void
}) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const label = rule.label[lang] || rule.label.es
  const when = rule.uses_offset ? t(`settings.rules.when.${rule.event}`, { count: rule.days_offset }) : t(`settings.rules.when.${rule.event}`)
  const listed = options.some((option) => option.code === rule.template_code)
  const templateChoices = listed ? options : [...options, { code: rule.template_code, label: rule.template_code, system: false, active: true }]

  function toggleChannel(channel: SendChannel, on: boolean) {
    const chosen = new Set(rule.channels)
    if (on) chosen.add(channel)
    else chosen.delete(channel)
    onSave({ channels: CHANNELS.filter((item) => chosen.has(item)) })
  }

  return (
    <div
      role="group"
      aria-label={label}
      className={cn('rounded-xl border border-border bg-surface p-4 shadow-xs transition-colors', !rule.enabled && 'bg-surface-2/50 shadow-none')}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="num mb-0.5 text-[11px] font-semibold text-muted sm:hidden">{markerText(rule, t)}</p>
          <h3 className={cn('text-[15px] leading-5 font-bold', !rule.enabled && 'text-muted')}>{label}</h3>
          <p className="mt-0.5 text-[13px] text-muted">{when}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn('text-[12px] font-semibold', rule.enabled ? 'text-accent-ink' : 'text-muted')} aria-hidden>
            {rule.enabled ? t('settings.rules.on') : t('settings.rules.off')}
          </span>
          <Switch
            aria-label={t('settings.rules.enabled')}
            checked={rule.enabled}
            disabled={!canEdit}
            onCheckedChange={(enabled) => onSave({ enabled })}
          />
        </div>
      </div>

      <div className={cn('mt-4 grid gap-4 sm:grid-cols-2', rule.uses_offset && rule.scheduled && 'xl:grid-cols-[auto_minmax(0,1fr)_auto_auto]', !rule.enabled && 'opacity-60')}>
        <fieldset className="grid gap-1.5">
          <legend className="mb-1.5 text-[13px] font-semibold">{t('settings.rules.channels')}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {CHANNELS.map((channel) => (
              <div key={channel} className="flex items-center gap-2">
                <Checkbox
                  id={`${ids}-${channel}`}
                  checked={rule.channels.includes(channel)}
                  disabled={!canEdit}
                  onCheckedChange={(value) => toggleChannel(channel, value === true)}
                />
                <Label htmlFor={`${ids}-${channel}`} className="font-normal">
                  {t(`channels.${channel}`)}
                </Label>
              </div>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-template`}>{t('settings.rules.template')}</Label>
          <Select value={rule.template_code} onValueChange={(template_code) => onSave({ template_code })} disabled={!canEdit} name="template_code">
            <SelectTrigger id={`${ids}-template`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {templateChoices.map((option) => (
                <SelectItem key={option.code} value={option.code}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Link
            to={`?tab=templates&template=${encodeURIComponent(rule.template_code)}`}
            className="inline-flex w-fit items-center gap-1 text-[12px] font-semibold text-accent-ink hover:underline"
          >
            {t('settings.rules.editText')}
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>

        {rule.uses_offset && (
          <CommitInput
            key={`offset-${rule.days_offset}`}
            label={t(`settings.rules.offsetLabel.${rule.event}`)}
            type="number"
            initial={String(rule.days_offset)}
            disabled={!canEdit}
            valid={(value) => /^\d+$/.test(value) && Number(value) <= MAX_OFFSET}
            onCommit={(value) => onSave({ days_offset: Number(value) })}
          />
        )}
        {rule.scheduled && (
          <CommitInput
            key={`time-${rule.send_after}`}
            label={t('settings.rules.sendAfter')}
            hint={t('settings.rules.sendAfterHint')}
            type="time"
            initial={rule.send_after}
            disabled={!canEdit}
            valid={(value) => /^\d{2}:\d{2}$/.test(value)}
            onCommit={(value) => onSave({ send_after: value })}
          />
        )}
      </div>

      {rule.enabled && rule.channels.length === 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-[12.5px] text-warning-ink">
          <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
          {t('settings.rules.noChannels')}
        </p>
      )}
    </div>
  )
}

/** A small field saved when it loses focus (or on Enter), only if its value changed and is valid. */
function CommitInput({
  label,
  hint,
  type,
  initial,
  disabled,
  valid,
  onCommit,
}: {
  label: string
  hint?: string
  type: 'number' | 'time'
  initial: string
  disabled: boolean
  valid: (value: string) => boolean
  onCommit: (value: string) => void
}) {
  const id = useId()
  const [value, setValue] = useState(initial)

  function commit() {
    const trimmed = value.trim()
    if (trimmed === initial) return
    if (!valid(trimmed)) {
      setValue(initial)
      return
    }
    onCommit(trimmed)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      commit()
    }
  }

  return (
    <div className="grid content-start gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        inputMode={type === 'number' ? 'numeric' : undefined}
        min={type === 'number' ? 0 : undefined}
        max={type === 'number' ? MAX_OFFSET : undefined}
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={onKeyDown}
        aria-describedby={hint ? `${id}-hint` : undefined}
        className={cn('num', type === 'number' ? 'w-24' : 'w-32')}
      />
      {hint && (
        <p id={`${id}-hint`} className="text-[12px] text-muted">
          {hint}
        </p>
      )}
    </div>
  )
}
