import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { normalizeLang } from '@/lib/format'
import { useSaveResource, type RatePlan, type RoomTypeDefaults, type RoomTypeOption, type Season, type SeasonRate } from '../../api'
import { adjustmentError, adjustmentsSchema, fromAdjustmentValues, toAdjustmentValues } from '../../lib/adjustments'
import { fieldErrors } from '../../lib/forms'
import { pick } from '../../lib/text'
import { FormDialog, MoneyField, TextField } from '../crud'
import { WeekdayAdjustmentsInput, WeekdayPreview } from './WeekdayAdjustments'

const MONEY = /^\d+(\.\d{1,2})?$/
const money = z.string().refine((value) => MONEY.test(value), 'validation.required')
const optionalMoney = z.string().refine((value) => value === '' || MONEY.test(value), 'validation.number')

// ---- Default price of a category in a base plan ------------------------------------------------------

const defaultsSchema = z.object({
  price: money,
  adjustments: adjustmentsSchema,
  extra_adult_price: optionalMoney,
  extra_child_price: optionalMoney,
  child_age_limit: z.string().refine((value) => /^\d{1,2}$/.test(value.trim()) && Number(value) <= 17, 'rates:plans.defaults.childAgeInvalid'),
  single_occupancy_price: optionalMoney,
})
type DefaultsValues = z.infer<typeof defaultsSchema>

const DEFAULTS_FIELDS = {
  price: 'price',
  extra_adult_price: 'extra_adult_price',
  extra_child_price: 'extra_child_price',
  child_age_limit: 'child_age_limit',
  single_occupancy_price: 'single_occupancy_price',
}

export interface DefaultsTarget {
  roomType: RoomTypeOption
  plan: RatePlan
  defaults: RoomTypeDefaults | null
}

/** Price of a category when no season or manual price applies, with weekday and occupancy adjustments. */
export function DefaultsDialog({
  open,
  onOpenChange,
  target,
  currency,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  target: DefaultsTarget
  currency: string
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const { roomType, plan, defaults } = target
  const isDorm = roomType.kind === 'dorm'
  const save = useSaveResource<RoomTypeDefaults>('room-type-defaults')
  const form = useForm<DefaultsValues>({
    resolver: zodResolver(defaultsSchema),
    defaultValues: {
      price: defaults?.price ?? '',
      adjustments: toAdjustmentValues(defaults?.dow_adjustments),
      extra_adult_price: defaults?.extra_adult_price ?? '',
      extra_child_price: defaults?.extra_child_price ?? '',
      child_age_limit: String(defaults?.child_age_limit ?? 12),
      single_occupancy_price: defaults?.single_occupancy_price ?? '',
    },
  })
  const [price, adjustments] = useWatch({ control: form.control, name: ['price', 'adjustments'] })
  const general = save.isError ? fieldErrors(save.error, DEFAULTS_FIELDS).general : null
  const roomTypeName = pick(roomType.name, lang)

  const submit = form.handleSubmit(async (values) => {
    const body = {
      room_type: roomType.id,
      rate_plan: plan.id,
      price: values.price,
      dow_adjustments: fromAdjustmentValues(values.adjustments),
      extra_adult_price: values.extra_adult_price || '0',
      extra_child_price: values.extra_child_price || '0',
      child_age_limit: Number(values.child_age_limit),
      single_occupancy_price: values.single_occupancy_price || null,
    }
    try {
      await save.mutateAsync(body)
      toast.success(t('plans.defaults.saved'))
      onOpenChange(false)
    } catch (error) {
      for (const [field, message] of Object.entries(fieldErrors(error, DEFAULTS_FIELDS).fields)) {
        form.setError(field as keyof DefaultsValues, { message })
      }
    }
  })

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('plans.defaults.dialogTitle', { roomType: roomTypeName })}
      description={t('plans.defaults.dialogHint', { plan: pick(plan.name, lang) })}
      submitLabel={t('plans.savePrice')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
      className="max-w-2xl"
    >
      <MoneyField
        control={form.control}
        name="price"
        label={t('plans.pricePerNight')}
        description={isDorm ? t('plans.defaults.perBed') : undefined}
        currency={currency}
        className="sm:w-56"
      />
      <Controller
        control={form.control}
        name="adjustments"
        render={({ field }) => (
          <WeekdayAdjustmentsInput
            value={field.value}
            onChange={field.onChange}
            error={adjustmentError(form.formState.errors.adjustments)}
          />
        )}
      />
      <WeekdayPreview price={price} adjustments={adjustments} currency={currency} />
      {isDorm ? (
        <p className="text-xs text-muted">{t('plans.defaults.dormHint')}</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <MoneyField
            control={form.control}
            name="extra_adult_price"
            label={t('plans.defaults.extraAdult')}
            description={t('plans.defaults.extraAdultHint', { count: roomType.base_occupancy })}
            currency={currency}
          />
          <MoneyField
            control={form.control}
            name="extra_child_price"
            label={t('plans.defaults.extraChild')}
            description={t('plans.defaults.extraChildHint')}
            currency={currency}
          />
          <TextField control={form.control} name="child_age_limit" label={t('plans.defaults.childAge')} inputMode="numeric" />
          <MoneyField
            control={form.control}
            name="single_occupancy_price"
            label={t('plans.defaults.single')}
            description={t('plans.defaults.singleHint')}
            currency={currency}
          />
        </div>
      )}
    </FormDialog>
  )
}

// ---- Price of a category during a season -----------------------------------------------------------

const seasonRateSchema = z.object({ price: money, adjustments: adjustmentsSchema })
type SeasonRateValues = z.infer<typeof seasonRateSchema>

export interface SeasonRateTarget {
  season: Season
  roomType: RoomTypeOption
  plan: RatePlan
  rate: Omit<SeasonRate, 'season'> | null
  /** Default price of the category (its weekday adjustments seed a new season price). */
  defaults: RoomTypeDefaults | null
}

export function SeasonRateDialog({
  open,
  onOpenChange,
  target,
  currency,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  target: SeasonRateTarget
  currency: string
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const { season, roomType, plan, rate, defaults } = target
  const save = useSaveResource<SeasonRate>('season-rates')
  const form = useForm<SeasonRateValues>({
    resolver: zodResolver(seasonRateSchema),
    defaultValues: {
      price: rate?.price ?? '',
      adjustments: toAdjustmentValues(rate ? rate.dow_adjustments : defaults?.dow_adjustments),
    },
  })
  const [price, adjustments] = useWatch({ control: form.control, name: ['price', 'adjustments'] })
  const general = save.isError ? fieldErrors(save.error, { price: 'price' }).general : null

  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync({
        season: season.id,
        room_type: roomType.id,
        rate_plan: plan.id,
        price: values.price,
        dow_adjustments: fromAdjustmentValues(values.adjustments),
      })
      toast.success(t('plans.seasons.rateSaved'))
      onOpenChange(false)
    } catch (error) {
      const { fields } = fieldErrors(error, { price: 'price' })
      if (fields.price) form.setError('price', { message: fields.price })
    }
  })

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('plans.seasons.rateDialogTitle', { roomType: pick(roomType.name, lang) })}
      description={t('plans.seasons.rateDialogHint', { season: season.name, plan: pick(plan.name, lang) })}
      submitLabel={t('plans.savePrice')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
      className="max-w-2xl"
    >
      <MoneyField control={form.control} name="price" label={t('plans.pricePerNight')} currency={currency} className="sm:w-56" />
      <Controller
        control={form.control}
        name="adjustments"
        render={({ field }) => (
          <WeekdayAdjustmentsInput
            value={field.value}
            onChange={field.onChange}
            error={adjustmentError(form.formState.errors.adjustments)}
          />
        )}
      />
      <WeekdayPreview price={price} adjustments={adjustments} currency={currency} />
    </FormDialog>
  )
}
