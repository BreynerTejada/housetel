import { zodResolver } from '@hookform/resolvers/zod'
import { Check } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { useId } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { useSaveResource, type Season } from '../../api'
import { fieldErrors } from '../../lib/forms'
import { addDays } from '../../lib/grid-utils'
import { DateField, FormDialog, TextField } from '../crud'

/** Muted season colors of the design system (the calendar tints them). */
const SEASON_COLORS = [
  { value: '#B98A2E', key: 'sand' },
  { value: '#4E6C88', key: 'slate' },
  { value: '#5F7F66', key: 'sage' },
  { value: '#B4583B', key: 'terracotta' },
  { value: '#7A5C7E', key: 'plum' },
  { value: '#857A6E', key: 'stone' },
] as const

const schema = z
  .object({
    name: z.string().trim().min(1, 'validation.required').max(100),
    start_date: z.string().nullable().refine(Boolean, 'validation.required'),
    end_date: z.string().nullable().refine(Boolean, 'validation.required'),
    priority: z.string().refine((value) => /^-?\d{1,4}$/.test(value.trim()), 'rates:plans.seasons.priorityInvalid'),
    color: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.start_date && values.end_date && values.end_date < values.start_date) {
      ctx.addIssue({ code: 'custom', path: ['end_date'], message: 'rates:plans.seasons.rangeInvalid' })
    }
  })
type Values = z.infer<typeof schema>

const FIELD_MAP = { name: 'name', start_date: 'start_date', end_date: 'end_date', priority: 'priority', color: 'color' }

/** Create or edit a season: name, first and last night (both included), priority and calendar color. */
export function SeasonDialog({
  open,
  onOpenChange,
  season,
  today,
  usedColors,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  season: Season | null
  /** Business date: a new season starts there and lasts a week. */
  today: string
  usedColors: string[]
  onSaved: (season: Season) => void
}) {
  const { t } = useTranslation('rates')
  const save = useSaveResource<Season>('seasons')
  const freeColor = SEASON_COLORS.find((color) => !usedColors.includes(color.value))?.value ?? SEASON_COLORS[0].value
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: season?.name ?? '',
      start_date: season?.start_date ?? today,
      end_date: season?.end_date ?? addDays(today, 6),
      priority: String(season?.priority ?? 0),
      color: season?.color ?? freeColor,
    },
  })
  const startDate = useWatch({ control: form.control, name: 'start_date' })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null

  const submit = form.handleSubmit(async (values) => {
    const body = {
      name: values.name.trim(),
      start_date: values.start_date as string,
      end_date: values.end_date as string,
      priority: Number(values.priority),
      color: values.color,
    }
    try {
      const saved = await save.mutateAsync(season ? { ...body, id: season.id } : body)
      toast.success(t(season ? 'plans.seasons.updated' : 'plans.seasons.created'))
      onSaved(saved)
      onOpenChange(false)
    } catch (error) {
      for (const [field, message] of Object.entries(fieldErrors(error, FIELD_MAP).fields)) {
        form.setError(field as keyof Values, { message })
      }
    }
  })

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t(season ? 'plans.seasons.edit' : 'plans.seasons.new')}
      description={t('plans.seasons.dialogHint')}
      submitLabel={t(season ? 'crud.save' : 'plans.seasons.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
    >
      <TextField control={form.control} name="name" label={t('fields.name')} />
      <div className="grid gap-4 sm:grid-cols-2">
        <DateField control={form.control} name="start_date" label={t('plans.seasons.firstNight')} clearable={false} />
        <DateField
          control={form.control}
          name="end_date"
          label={t('plans.seasons.lastNight')}
          description={t('plans.seasons.lastNightHint')}
          min={startDate}
          clearable={false}
        />
      </div>
      <TextField
        control={form.control}
        name="priority"
        label={t('plans.seasons.priority')}
        description={t('plans.seasons.priorityHint')}
        inputMode="numeric"
        className="sm:w-48"
      />
      <Controller
        control={form.control}
        name="color"
        render={({ field }) => <ColorChoice value={field.value} onChange={field.onChange} />}
      />
    </FormDialog>
  )
}

function ColorChoice({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation('rates')
  const id = useId()
  const options = SEASON_COLORS.some((color) => color.value.toLowerCase() === value.toLowerCase())
    ? SEASON_COLORS.map((color) => ({ value: color.value, label: t(`plans.seasons.colors.${color.key}`) }))
    : [...SEASON_COLORS.map((color) => ({ value: color.value, label: t(`plans.seasons.colors.${color.key}`) })), { value, label: t('plans.seasons.colors.current') }]
  return (
    <fieldset className="grid gap-2">
      <legend id={`${id}-legend`} className="mb-2 text-[13px] leading-5 font-semibold text-fg">
        {t('plans.seasons.color')}
      </legend>
      <RadioGroupPrimitive.Root
        value={value}
        onValueChange={onChange}
        aria-labelledby={`${id}-legend`}
        className="flex flex-wrap gap-2.5"
      >
        {options.map((option) => (
          <RadioGroupPrimitive.Item
            key={option.value}
            value={option.value}
            aria-label={option.label}
            title={option.label}
            className="grid size-8 place-items-center rounded-full border-2 border-surface shadow-[0_0_0_1px_var(--border)] transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-surface data-[state=checked]:shadow-[0_0_0_2px_var(--text)]"
            style={{ backgroundColor: option.value }}
          >
            <RadioGroupPrimitive.Indicator>
              <Check aria-hidden className="size-4 text-white" strokeWidth={3} />
            </RadioGroupPrimitive.Indicator>
          </RadioGroupPrimitive.Item>
        ))}
      </RadioGroupPrimitive.Root>
    </fieldset>
  )
}
