import { zodResolver } from '@hookform/resolvers/zod'
import type { ColumnDef } from '@tanstack/react-table'
import { Plus, ShieldCheck } from 'lucide-react'
import { useMemo } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { DataTable } from '@/components/DataTable'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useDeleteResource, useRatesList, useSaveResource, type CancellationPolicy, type PenaltyType } from '../api'
import { FormDialog, RowActions, SelectField, SwitchField, TextField } from '../components/crud'
import { useEditor } from '../hooks/useEditor'
import { fieldErrors, parseDecimal, toI18n } from '../lib/forms'
import { pick } from '../lib/text'

const PENALTIES = ['first_night', 'percent', 'full'] as const

const schema = z
  .object({
    name_es: z.string().trim().min(1, 'validation.required').max(100),
    name_en: z.string().trim().max(100),
    non_refundable: z.boolean(),
    free_until_hours_before: z.string(),
    penalty_type: z.enum(PENALTIES),
    penalty_value: z.string(),
    description_es: z.string().trim().max(1000),
    description_en: z.string().trim().max(1000),
  })
  .superRefine((values, ctx) => {
    if (!values.non_refundable && !/^\d{1,4}$/.test(values.free_until_hours_before.trim())) {
      ctx.addIssue({ code: 'custom', path: ['free_until_hours_before'], message: 'rates:policies.hoursInvalid' })
    }
    if (!values.non_refundable && values.penalty_type === 'percent') {
      const percent = parseDecimal(values.penalty_value, { signed: false })
      if (percent === null || Number(percent) > 100) {
        ctx.addIssue({ code: 'custom', path: ['penalty_value'], message: 'rates:taxes.rateInvalid' })
      }
    }
  })
type Values = z.infer<typeof schema>

const FIELD_MAP = {
  name: 'name_es',
  non_refundable: 'non_refundable',
  free_until_hours_before: 'free_until_hours_before',
  penalty_type: 'penalty_type',
  penalty_value: 'penalty_value',
  description: 'description_es',
}

function toValues(policy: CancellationPolicy | null): Values {
  return {
    name_es: policy?.name.es ?? '',
    name_en: policy?.name.en ?? '',
    non_refundable: policy?.non_refundable ?? false,
    free_until_hours_before: String(policy?.free_until_hours_before ?? 48),
    penalty_type: policy?.penalty_type ?? 'first_night',
    penalty_value: policy && policy.penalty_type === 'percent' ? String(Number(policy.penalty_value)) : '',
    description_es: policy?.description?.es ?? '',
    description_en: policy?.description?.en ?? '',
  }
}

function toBody(values: Values) {
  const nonRefundable = values.non_refundable
  const penaltyType: PenaltyType = nonRefundable ? 'full' : values.penalty_type
  return {
    name: toI18n(values.name_es, values.name_en),
    non_refundable: nonRefundable,
    free_until_hours_before: nonRefundable ? 0 : Number(values.free_until_hours_before),
    penalty_type: penaltyType,
    penalty_value: penaltyType === 'percent' ? (parseDecimal(values.penalty_value, { signed: false }) ?? '0') : '0',
    description: toI18n(values.description_es, values.description_en),
  }
}

/** `/app/settings/policies`: free-cancellation windows and penalties of the rate plans. */
export default function PoliciesPage() {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const query = useRatesList<CancellationPolicy>('cancellation-policies')
  const remove = useDeleteResource('cancellation-policies')
  const editor = useEditor<CancellationPolicy>()

  const columns = useMemo<ColumnDef<CancellationPolicy>[]>(
    () => [
      {
        id: 'name',
        header: t('fields.name'),
        accessorFn: (policy) => pick(policy.name, lang),
        cell: ({ row }) => (
          <div className="grid gap-0.5">
            <span className="font-semibold">{pick(row.original.name, lang)}</span>
            {pick(row.original.description, lang) && (
              <span className="line-clamp-1 text-xs text-muted">{pick(row.original.description, lang)}</span>
            )}
          </div>
        ),
      },
      {
        id: 'window',
        header: t('policies.window'),
        cell: ({ row }) =>
          row.original.non_refundable ? (
            <Badge tone="warning">{t('policies.noRefund')}</Badge>
          ) : (
            t('policies.freeUntil', { hours: row.original.free_until_hours_before })
          ),
      },
      {
        id: 'penalty',
        header: t('policies.penalty'),
        cell: ({ row }) =>
          row.original.penalty_type === 'percent'
            ? t('policies.percentOf', { value: Number(row.original.penalty_value) })
            : t(`policies.penalties.${row.original.penalty_type}`),
      },
      {
        id: 'plans',
        header: t('policies.plans'),
        meta: { align: 'right' },
        cell: ({ row }) => t('policies.plansCount', { count: row.original.plans_count }),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">{t('crud.actions')}</span>,
        meta: { align: 'right' },
        cell: ({ row }) => (
          <RowActions
            name={pick(row.original.name, lang)}
            canEdit={canManage}
            onEdit={() => editor.edit(row.original)}
            onDelete={async () => {
              await remove.mutateAsync(row.original.id)
              toast.success(t('policies.deleted'))
            }}
          />
        ),
      },
    ],
    [t, lang, canManage, editor, remove],
  )

  return (
    <div>
      <PageHeader
        title={t('policies.title')}
        description={t('policies.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={editor.create}>
              <Plus aria-hidden />
              {t('policies.new')}
            </Button>
          )
        }
      />
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('policies.title')}
          columns={columns}
          data={query.data ?? []}
          isLoading={query.isPending}
          getRowId={(row) => row.id}
          empty={<EmptyState icon={ShieldCheck} title={t('policies.empty')} description={t('policies.emptyHint')} />}
        />
      )}
      <PolicyDialog key={editor.key} open={editor.open} policy={editor.item} onOpenChange={editor.setOpen} />
    </div>
  )
}

function PolicyDialog({
  open,
  policy,
  onOpenChange,
}: {
  open: boolean
  policy: CancellationPolicy | null
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation('rates')
  const save = useSaveResource<CancellationPolicy>('cancellation-policies')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(policy) })
  const [nonRefundable, penaltyType] = useWatch({ control: form.control, name: ['non_refundable', 'penalty_type'] })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null

  const submit = form.handleSubmit(async (values) => {
    try {
      const body = toBody(values)
      await save.mutateAsync(policy ? { ...body, id: policy.id } : body)
      toast.success(t(policy ? 'policies.updated' : 'policies.created'))
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
      title={t(policy ? 'policies.edit' : 'policies.new')}
      description={t('policies.dialogHint')}
      submitLabel={t(policy ? 'crud.save' : 'policies.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField control={form.control} name="name_es" label={t('fields.nameEs')} />
        <TextField control={form.control} name="name_en" label={t('fields.nameEn')} />
      </div>
      <SwitchField
        control={form.control}
        name="non_refundable"
        label={t('policies.nonRefundable')}
        description={t('policies.nonRefundableHint')}
      />
      {!nonRefundable && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            control={form.control}
            name="free_until_hours_before"
            label={t('policies.hours')}
            inputMode="numeric"
            description={t('policies.hoursHint')}
          />
          <SelectField
            control={form.control}
            name="penalty_type"
            label={t('policies.penalty')}
            options={PENALTIES.map((value) => ({ value, label: t(`policies.penalties.${value}`) }))}
          />
          {penaltyType === 'percent' && (
            <TextField control={form.control} name="penalty_value" label={t('policies.percentLabel')} inputMode="decimal" />
          )}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField control={form.control} name="description_es" label={t('fields.descriptionEs')} />
        <TextField control={form.control} name="description_en" label={t('fields.descriptionEn')} />
      </div>
    </FormDialog>
  )
}
