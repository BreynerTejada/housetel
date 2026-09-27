import { zodResolver } from '@hookform/resolvers/zod'
import type { ColumnDef } from '@tanstack/react-table'
import type { TFunction } from 'i18next'
import { Plus, TicketPercent } from 'lucide-react'
import { useMemo } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { DataTable } from '@/components/DataTable'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { PageHeader } from '@/components/PageHeader'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, formatDateRange, formatMoney, formatNumber, normalizeLang, type Lang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useDeleteResource, useRatesList, useSaveResource, type PromoCode, type RatePlan } from '../api'
import {
  CheckboxGroupField,
  DateField,
  FormDialog,
  MoneyField,
  RadioField,
  RowActions,
  SwitchField,
  TextField,
} from '../components/crud'
import { useEditor } from '../hooks/useEditor'
import { fieldErrors, parseDecimal } from '../lib/forms'
import { promoState, type PromoState } from '../lib/promos'
import { pick } from '../lib/text'

const DISCOUNT_TYPES = ['percent', 'amount'] as const
const CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$/

const schema = z
  .object({
    code: z.string().trim().regex(CODE_PATTERN, 'rates:promos.codeInvalid'),
    discount_type: z.enum(DISCOUNT_TYPES),
    value: z.string(),
    valid_from: z.string().nullable(),
    valid_to: z.string().nullable(),
    stay_from: z.string().nullable(),
    stay_to: z.string().nullable(),
    rate_plans: z.array(z.string()),
    max_uses: z.string().refine((value) => value.trim() === '' || /^[1-9]\d*$/.test(value.trim()), 'rates:promos.maxUsesInvalid'),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.discount_type === 'percent') {
      const percent = parseDecimal(values.value, { signed: false })
      if (percent === null || Number(percent) < 1 || Number(percent) > 100) {
        ctx.addIssue({ code: 'custom', path: ['value'], message: 'rates:promos.percentInvalid' })
      }
    } else if (!/^\d+$/.test(values.value) || Number(values.value) <= 0) {
      ctx.addIssue({ code: 'custom', path: ['value'], message: 'rates:promos.amountInvalid' })
    }
    for (const [first, last] of [
      ['valid_from', 'valid_to'],
      ['stay_from', 'stay_to'],
    ] as const) {
      const from = values[first]
      const to = values[last]
      if (from && to && to < from) ctx.addIssue({ code: 'custom', path: [last], message: 'rates:promos.rangeInvalid' })
    }
  })
type Values = z.infer<typeof schema>

const FIELD_MAP: Record<string, string> = Object.fromEntries(Object.keys(schema.shape).map((key) => [key, key]))

function toValues(promo: PromoCode | null): Values {
  return {
    code: promo?.code ?? '',
    discount_type: promo?.discount_type ?? 'percent',
    value: promo ? String(Number(promo.value)) : '',
    valid_from: promo?.valid_from ?? null,
    valid_to: promo?.valid_to ?? null,
    stay_from: promo?.stay_from ?? null,
    stay_to: promo?.stay_to ?? null,
    rate_plans: promo?.rate_plans ?? [],
    max_uses: promo?.max_uses ? String(promo.max_uses) : '',
    is_active: promo?.is_active ?? true,
  }
}

function toBody(values: Values) {
  return {
    code: values.code.trim().toUpperCase(),
    discount_type: values.discount_type,
    value: values.discount_type === 'percent' ? (parseDecimal(values.value, { signed: false }) ?? values.value) : values.value,
    valid_from: values.valid_from,
    valid_to: values.valid_to,
    stay_from: values.stay_from,
    stay_to: values.stay_to,
    rate_plans: values.rate_plans,
    max_uses: values.max_uses.trim() ? Number(values.max_uses) : null,
    is_active: values.is_active,
  }
}

/** "1 sep – 31 dic 2026", "Desde 1 sep 2026", "Hasta 31 dic 2026" or "Cualquier fecha" (both ends inclusive). */
function windowLabel(from: string | null, to: string | null, lang: Lang, t: TFunction<'rates'>) {
  if (from && to) return formatDateRange(from, to, lang)
  if (from) return t('promos.since', { date: formatDate(from, undefined, lang) })
  if (to) return t('promos.until', { date: formatDate(to, undefined, lang) })
  return t('promos.anyDate')
}

const STATE_TONES: Record<PromoState, BadgeTone> = {
  active: 'success',
  inactive: 'stone',
  expired: 'neutral',
  exhausted: 'warning',
  scheduled: 'info',
}

/** `/app/rates/promos`: discount codes for the booking engine, the marketplace and front desk. */
export default function PromosPage() {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const { property } = useActiveProperty()
  const currency = property?.currency ?? 'COP'
  const today = property?.business_date ?? ''
  const query = useRatesList<PromoCode>('promo-codes')
  const plans = useRatesList<RatePlan>('rate-plans')
  const remove = useDeleteResource('promo-codes')
  const editor = useEditor<PromoCode>()
  const planNames = useMemo(() => new Map((plans.data ?? []).map((plan) => [plan.id, pick(plan.name, lang)])), [plans.data, lang])

  const columns = useMemo<ColumnDef<PromoCode>[]>(
    () => [
      {
        accessorKey: 'code',
        header: t('promos.code'),
        cell: ({ row }) => <span className="font-bold tracking-wide">{row.original.code}</span>,
      },
      {
        id: 'discount',
        header: t('promos.discount'),
        meta: { align: 'right' },
        cell: ({ row }) =>
          row.original.discount_type === 'percent' ? (
            <span className="num font-semibold">{`${formatNumber(Number(row.original.value), lang)} %`}</span>
          ) : (
            <span className="num font-semibold">{t('promos.perNight', { amount: formatMoney(row.original.value, currency) })}</span>
          ),
      },
      {
        id: 'booking',
        header: t('promos.bookingWindow'),
        cell: ({ row }) => <span className="num">{windowLabel(row.original.valid_from, row.original.valid_to, lang, t)}</span>,
      },
      {
        id: 'stay',
        header: t('promos.stayWindow'),
        cell: ({ row }) => <span className="num">{windowLabel(row.original.stay_from, row.original.stay_to, lang, t)}</span>,
      },
      {
        id: 'plans',
        header: t('promos.plans'),
        cell: ({ row }) =>
          row.original.rate_plans.length === 0
            ? t('promos.allPlans')
            : row.original.rate_plans.map((id) => planNames.get(id) ?? '—').join(', '),
      },
      {
        id: 'uses',
        header: t('promos.uses'),
        meta: { align: 'right' },
        cell: ({ row }) => (
          <span className="num">
            {row.original.max_uses === null
              ? t('promos.usesCount', { count: row.original.uses })
              : t('promos.usesOf', { uses: row.original.uses, max: row.original.max_uses })}
          </span>
        ),
      },
      {
        id: 'state',
        header: t('promos.state'),
        cell: ({ row }) => {
          const state = promoState(row.original, today)
          return <Badge tone={STATE_TONES[state]}>{t(`promos.states.${state}`)}</Badge>
        },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">{t('crud.actions')}</span>,
        meta: { align: 'right' },
        cell: ({ row }) => (
          <RowActions
            name={row.original.code}
            canEdit={canManage}
            onEdit={() => editor.edit(row.original)}
            onDelete={async () => {
              await remove.mutateAsync(row.original.id)
              toast.success(t('promos.deleted'))
            }}
          />
        ),
      },
    ],
    [t, lang, currency, today, planNames, canManage, editor, remove],
  )

  return (
    <div>
      <PageHeader
        title={t('promos.title')}
        description={t('promos.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={editor.create}>
              <Plus aria-hidden />
              {t('promos.new')}
            </Button>
          )
        }
      />
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('promos.title')}
          columns={columns}
          data={query.data ?? []}
          isLoading={query.isPending}
          getRowId={(row) => row.id}
          empty={<EmptyState icon={TicketPercent} title={t('promos.empty')} description={t('promos.emptyHint')} />}
        />
      )}
      <PromoDialog
        key={editor.key}
        open={editor.open}
        promo={editor.item}
        plans={plans.data ?? []}
        currency={currency}
        onOpenChange={editor.setOpen}
      />
    </div>
  )
}

function PromoDialog({
  open,
  promo,
  plans,
  currency,
  onOpenChange,
}: {
  open: boolean
  promo: PromoCode | null
  plans: RatePlan[]
  currency: string
  onOpenChange: (open: boolean) => void
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const save = useSaveResource<PromoCode>('promo-codes')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(promo) })
  const [discountType, validFrom, stayFrom] = useWatch({ control: form.control, name: ['discount_type', 'valid_from', 'stay_from'] })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null

  const submit = form.handleSubmit(async (values) => {
    const body = toBody(values)
    try {
      await save.mutateAsync(promo ? { ...body, id: promo.id } : body)
      toast.success(t(promo ? 'promos.updated' : 'promos.created'))
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
      title={t(promo ? 'promos.edit' : 'promos.new')}
      description={t('promos.dialogHint')}
      submitLabel={t(promo ? 'crud.save' : 'promos.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
      className="max-w-2xl"
    >
      <FormField
        control={form.control}
        name="code"
        label={t('promos.code')}
        description={t('promos.codeHint')}
        className="sm:w-64"
        render={({ field, ...a11y }) => (
          <Input
            {...field}
            {...a11y}
            onChange={(event) => field.onChange(event.target.value.toUpperCase())}
            autoComplete="off"
            className="font-semibold tracking-wide"
          />
        )}
      />
      <RadioField
        control={form.control}
        name="discount_type"
        label={t('promos.discountType')}
        options={DISCOUNT_TYPES.map((value) => ({ value, label: t(`promos.types.${value}`) }))}
        onValueChange={() => form.setValue('value', '')}
      />
      {discountType === 'percent' ? (
        <TextField control={form.control} name="value" label={t('promos.percentLabel')} inputMode="decimal" className="sm:w-48" />
      ) : (
        <MoneyField control={form.control} name="value" label={t('promos.amountLabel')} currency={currency} className="sm:w-48" />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <DateField control={form.control} name="valid_from" label={t('promos.validFrom')} />
        <DateField control={form.control} name="valid_to" label={t('promos.validTo')} min={validFrom} />
      </div>
      <p className="-mt-2 text-xs text-muted">{t('promos.bookingWindowHint')}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <DateField control={form.control} name="stay_from" label={t('promos.stayFrom')} />
        <DateField control={form.control} name="stay_to" label={t('promos.stayTo')} min={stayFrom} />
      </div>
      <p className="-mt-2 text-xs text-muted">{t('promos.stayWindowHint')}</p>
      <CheckboxGroupField
        control={form.control}
        name="rate_plans"
        label={t('promos.plans')}
        emptyHint={t('promos.allPlansHint')}
        options={plans.map((plan) => ({ value: plan.id, label: pick(plan.name, lang), hint: plan.code }))}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          control={form.control}
          name="max_uses"
          label={t('promos.maxUses')}
          description={t('promos.maxUsesHint')}
          inputMode="numeric"
        />
      </div>
      <SwitchField control={form.control} name="is_active" label={t('fields.active')} description={t('promos.activeHint')} />
    </FormDialog>
  )
}
