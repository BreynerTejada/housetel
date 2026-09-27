import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useSaveResource, type DerivationType, type MealPlan, type RatePlan } from '../../api'
import type { PlansData } from '../../hooks/usePlansData'
import { fieldErrors, parseDecimal, toI18n } from '../../lib/forms'
import { derivedPrice, KNOWN_CHANNELS } from '../../lib/plans'
import { pick } from '../../lib/text'
import { CheckboxGroupField, FormDialog, RadioField, SelectField, SwitchField, TextField } from '../crud'

const MEAL_PLANS: MealPlan[] = ['room_only', 'breakfast', 'half_board', 'full_board', 'all_inclusive']
const NO_POLICY = 'none'

const schema = z
  .object({
    kind: z.enum(['base', 'derived']),
    parent: z.string(),
    derivation_type: z.enum(['percent', 'amount']),
    derivation_value: z.string(),
    code: z.string().trim().min(1, 'validation.required').max(20),
    name_es: z.string().trim().min(1, 'validation.required').max(100),
    name_en: z.string().trim().max(100),
    room_types: z.array(z.string()),
    meal_plan: z.enum(['room_only', 'breakfast', 'half_board', 'full_board', 'all_inclusive']),
    cancellation_policy: z.string(),
    deposit_percent: z.string().refine((value) => {
      const percent = parseDecimal(value, { signed: false })
      return percent !== null && Number(percent) <= 100
    }, 'rates:taxes.rateInvalid'),
    min_los_default: z.string().refine((value) => /^\d{1,3}$/.test(value.trim()) && Number(value) >= 1 && Number(value) <= 365, 'rates:plans.editor.minLosInvalid'),
    is_public: z.boolean(),
    all_channels: z.boolean(),
    channels: z.array(z.string()),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.kind === 'derived') {
      if (!values.parent) ctx.addIssue({ code: 'custom', path: ['parent'], message: 'rates:plans.editor.parentRequired' })
      const value = parseDecimal(values.derivation_value)
      if (value === null) {
        ctx.addIssue({ code: 'custom', path: ['derivation_value'], message: 'rates:plans.editor.adjustmentNumber' })
      } else if (values.derivation_type === 'percent' && Number(value) < -100) {
        ctx.addIssue({ code: 'custom', path: ['derivation_value'], message: 'rates:plans.editor.discountTooBig' })
      }
    }
    if (!values.all_channels && values.channels.length === 0) {
      ctx.addIssue({ code: 'custom', path: ['channels'], message: 'rates:plans.editor.channelsRequired' })
    }
  })
type Values = z.infer<typeof schema>

const FIELD_MAP: Record<string, string> = {
  code: 'code',
  name: 'name_es',
  kind: 'kind',
  parent: 'parent',
  derivation_type: 'derivation_type',
  derivation_value: 'derivation_value',
  room_types: 'room_types',
  meal_plan: 'meal_plan',
  cancellation_policy: 'cancellation_policy',
  deposit_percent: 'deposit_percent',
  min_los_default: 'min_los_default',
  channels: 'channels',
}

export interface PlanDialogState {
  open: boolean
  /** Plan being edited, or null to create one. */
  plan: RatePlan | null
  /** Base plan of a new derived plan. */
  parentId: string | null
  key: number
}

function initialValues(plan: RatePlan | null, parent: RatePlan | null, data: PlansData): Values {
  if (plan) {
    return {
      kind: plan.kind,
      parent: plan.parent ?? '',
      derivation_type: plan.derivation_type || 'percent',
      derivation_value: plan.kind === 'derived' ? String(Number(plan.derivation_value)) : '',
      code: plan.code,
      name_es: plan.name.es ?? '',
      name_en: plan.name.en ?? '',
      room_types: plan.room_types,
      meal_plan: plan.meal_plan,
      cancellation_policy: plan.cancellation_policy ?? NO_POLICY,
      deposit_percent: String(Number(plan.deposit_percent)),
      min_los_default: String(plan.min_los_default),
      is_public: plan.is_public,
      all_channels: plan.channels.length === 0,
      channels: plan.channels,
      is_active: plan.is_active,
    }
  }
  return {
    kind: parent ? 'derived' : 'base',
    parent: parent?.id ?? '',
    derivation_type: 'percent',
    derivation_value: '',
    code: '',
    name_es: '',
    name_en: '',
    room_types: parent ? parent.room_types : data.roomTypes.filter((roomType) => roomType.is_active).map((roomType) => roomType.id),
    meal_plan: 'room_only',
    cancellation_policy: parent?.cancellation_policy ?? NO_POLICY,
    deposit_percent: '0',
    min_los_default: '1',
    is_public: true,
    all_channels: true,
    channels: [],
    is_active: true,
  }
}

function toBody(values: Values) {
  const derived = values.kind === 'derived'
  return {
    code: values.code.trim(),
    name: toI18n(values.name_es, values.name_en),
    kind: values.kind,
    parent: derived ? values.parent : null,
    derivation_type: (derived ? values.derivation_type : 'percent') as DerivationType,
    derivation_value: derived ? (parseDecimal(values.derivation_value) ?? '0') : '0',
    room_types: values.room_types,
    meal_plan: values.meal_plan,
    cancellation_policy: values.cancellation_policy === NO_POLICY ? null : values.cancellation_policy,
    deposit_percent: parseDecimal(values.deposit_percent, { signed: false }) ?? '0',
    min_los_default: Number(values.min_los_default),
    is_public: values.is_public,
    channels: values.all_channels ? [] : values.channels,
    is_active: values.is_active,
  }
}

/** Create or edit a rate plan. A derived plan shows, while typing, the price it gives to each category. */
export function PlanDialog({
  state,
  onOpenChange,
  data,
  currency,
}: {
  state: PlanDialogState
  onOpenChange: (open: boolean) => void
  data: PlansData
  currency: string
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const { plan } = state
  const initialParent = data.basePlans.find((item) => item.id === state.parentId) ?? null
  const save = useSaveResource<RatePlan>('rate-plans')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initialValues(plan, initialParent, data) })
  const [kind, parentId, derivationType, derivationValue, allChannels, channels] = useWatch({
    control: form.control,
    name: ['kind', 'parent', 'derivation_type', 'derivation_value', 'all_channels', 'channels'],
  })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null
  const parent = data.basePlans.find((item) => item.id === parentId) ?? null
  const derived = kind === 'derived'

  const roomTypeOptions = (derived ? data.roomTypes.filter((roomType) => parent?.room_types.includes(roomType.id)) : data.roomTypes)
    .filter((roomType) => roomType.is_active || form.getValues('room_types').includes(roomType.id))
    .map((roomType) => ({ value: roomType.id, label: pick(roomType.name, lang), hint: roomType.code, color: roomType.color }))
  const channelCodes = [...KNOWN_CHANNELS, ...channels.filter((code) => !(KNOWN_CHANNELS as readonly string[]).includes(code))]
  const channelOptions = channelCodes.map((code) => ({
    value: code,
    label: (KNOWN_CHANNELS as readonly string[]).includes(code) ? t(`plans.channels.${code}`) : code,
  }))

  const value = parseDecimal(derivationValue)
  const preview =
    derived && parent && value !== null
      ? data.roomTypes
          .filter((roomType) => parent.room_types.includes(roomType.id))
          .map((roomType) => ({ roomType, defaults: data.defaultsFor(roomType.id, parent.id) }))
          .filter((item) => item.defaults)
          .slice(0, 4)
          .map(({ roomType, defaults }) => {
            const base = defaults!.price
            const result = derivedPrice(base, { derivation_type: derivationType, derivation_value: value }, currency)
            return `${pick(roomType.name, lang)}: ${formatMoney(base, currency)} → ${formatMoney(result, currency)}`
          })
      : []

  function chooseParent(id: string) {
    const next = data.basePlans.find((item) => item.id === id)
    form.setValue('room_types', next?.room_types ?? [])
  }

  function chooseKind(next: string) {
    if (next === 'derived') {
      const first = parent ?? data.basePlans[0] ?? null
      form.setValue('parent', first?.id ?? '')
      form.setValue('room_types', first?.room_types ?? [])
    } else {
      form.setValue('room_types', data.roomTypes.filter((roomType) => roomType.is_active).map((roomType) => roomType.id))
    }
  }

  const submit = form.handleSubmit(async (values) => {
    const body = toBody(values)
    try {
      await save.mutateAsync(plan ? { ...body, id: plan.id } : body)
      toast.success(t(plan ? 'plans.editor.updated' : 'plans.editor.created'))
      onOpenChange(false)
    } catch (error) {
      for (const [field, message] of Object.entries(fieldErrors(error, FIELD_MAP).fields)) {
        form.setError(field as keyof Values, { message })
      }
    }
  })

  return (
    <FormDialog
      open={state.open}
      onOpenChange={onOpenChange}
      title={t(plan ? 'plans.editor.edit' : 'plans.editor.new')}
      description={t(derived ? 'plans.editor.derivedHint' : 'plans.editor.baseHint')}
      submitLabel={t(plan ? 'crud.save' : 'plans.editor.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
      className="max-w-2xl"
    >
      {!plan && data.basePlans.length > 0 && (
        <RadioField
          control={form.control}
          name="kind"
          label={t('plans.editor.kind')}
          options={[
            { value: 'base', label: t('plans.editor.kinds.base') },
            { value: 'derived', label: t('plans.editor.kinds.derived') },
          ]}
          onValueChange={chooseKind}
        />
      )}

      {derived && (
        <div className="grid gap-4 rounded-lg border border-border bg-surface-2/60 p-4">
          <SelectField
            control={form.control}
            name="parent"
            label={t('plans.editor.parent')}
            options={data.basePlans.filter((item) => item.id !== plan?.id).map((item) => ({ value: item.id, label: pick(item.name, lang) }))}
            onValueChange={chooseParent}
          />
          <RadioField
            control={form.control}
            name="derivation_type"
            label={t('plans.editor.rule')}
            options={[
              { value: 'percent', label: t('plans.editor.rules.percent') },
              { value: 'amount', label: t('plans.editor.rules.amount') },
            ]}
          />
          <TextField
            control={form.control}
            name="derivation_value"
            label={t(derivationType === 'percent' ? 'plans.editor.percentValue' : 'plans.editor.amountValue')}
            description={t(derivationType === 'percent' ? 'plans.editor.percentHint' : 'plans.editor.amountHint')}
            inputMode="decimal"
            className="sm:w-56"
          />
          {preview.length > 0 && (
            <div className="grid gap-1">
              <span className="eyebrow">{t('plans.editor.preview')}</span>
              <ul className="num grid gap-0.5 text-[13px] text-fg">
                {preview.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-[8rem_1fr_1fr]">
        <TextField control={form.control} name="code" label={t('fields.code')} />
        <TextField control={form.control} name="name_es" label={t('fields.nameEs')} />
        <TextField control={form.control} name="name_en" label={t('fields.nameEn')} />
      </div>

      <CheckboxGroupField
        control={form.control}
        name="room_types"
        label={t('plans.editor.roomTypes')}
        description={derived ? t('plans.editor.roomTypesDerivedHint') : undefined}
        emptyHint={t('plans.editor.roomTypesEmpty')}
        options={roomTypeOptions}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          control={form.control}
          name="meal_plan"
          label={t('plans.editor.mealPlan')}
          options={MEAL_PLANS.map((meal) => ({ value: meal, label: t(`plans.meals.${meal}`) }))}
        />
        <SelectField
          control={form.control}
          name="cancellation_policy"
          label={t('plans.editor.policy')}
          options={[
            { value: NO_POLICY, label: t('plans.editor.noPolicy') },
            ...data.policies.map((policy) => ({ value: policy.id, label: pick(policy.name, lang) })),
          ]}
        />
        <TextField
          control={form.control}
          name="deposit_percent"
          label={t('plans.editor.deposit')}
          description={t('plans.editor.depositHint')}
          inputMode="decimal"
        />
        <TextField
          control={form.control}
          name="min_los_default"
          label={t('plans.editor.minLos')}
          description={t('plans.editor.minLosHint')}
          inputMode="numeric"
        />
      </div>

      <SwitchField control={form.control} name="is_public" label={t('plans.editor.public')} description={t('plans.editor.publicHint')} />
      <SwitchField
        control={form.control}
        name="all_channels"
        label={t('plans.editor.allChannels')}
        description={t('plans.editor.allChannelsHint')}
      />
      {!allChannels && (
        <CheckboxGroupField control={form.control} name="channels" label={t('plans.editor.channels')} options={channelOptions} />
      )}
      <SwitchField control={form.control} name="is_active" label={t('fields.active')} description={t('plans.editor.activeHint')} />
    </FormDialog>
  )
}
