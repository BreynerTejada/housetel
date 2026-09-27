import { zodResolver } from '@hookform/resolvers/zod'
import type { ColumnDef } from '@tanstack/react-table'
import { Coffee, Plus } from 'lucide-react'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { DataTable } from '@/components/DataTable'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useActiveProperty } from '@/lib/auth'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useDeleteResource, useRatesList, useSaveResource, type Extra, type Tax } from '../api'
import { FormDialog, MoneyField, RowActions, SelectField, SwitchField, TextField } from '../components/crud'
import { useEditor } from '../hooks/useEditor'
import { fieldErrors, toI18n } from '../lib/forms'
import { pick } from '../lib/text'

const CHARGE_TYPES = ['per_stay', 'per_night', 'per_person', 'per_person_night'] as const
const NO_TAX = 'none'

const schema = z.object({
  code: z.string().trim().min(1, 'validation.required').max(20),
  name_es: z.string().trim().min(1, 'validation.required').max(100),
  name_en: z.string().trim().max(100),
  price: z.string().min(1, 'validation.required'),
  charge_type: z.enum(CHARGE_TYPES),
  tax: z.string(),
  sellable_online: z.boolean(),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

const FIELD_MAP = {
  code: 'code',
  name: 'name_es',
  price: 'price',
  charge_type: 'charge_type',
  tax: 'tax',
}

function toValues(extra: Extra | null): Values {
  return {
    code: extra?.code ?? '',
    name_es: extra?.name.es ?? '',
    name_en: extra?.name.en ?? '',
    price: extra ? String(Math.round(Number(extra.price))) : '',
    charge_type: extra?.charge_type ?? 'per_stay',
    tax: extra?.tax ?? NO_TAX,
    sellable_online: extra?.sellable_online ?? true,
    is_active: extra?.is_active ?? true,
  }
}

/** `/app/settings/extras`: services charged apart (breakfast, parking, transfers…). */
export default function ExtrasPage() {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const { property } = useActiveProperty()
  const currency = property?.currency ?? 'COP'
  const query = useRatesList<Extra>('extras')
  const taxes = useRatesList<Tax>('taxes')
  const remove = useDeleteResource('extras')
  const editor = useEditor<Extra>()
  const taxNames = useMemo(() => new Map((taxes.data ?? []).map((tax) => [tax.id, tax.name])), [taxes.data])

  const columns = useMemo<ColumnDef<Extra>[]>(
    () => [
      { accessorKey: 'code', header: t('fields.code'), cell: ({ row }) => <span className="font-semibold">{row.original.code}</span> },
      { id: 'name', header: t('fields.name'), accessorFn: (extra) => pick(extra.name, lang) },
      {
        accessorKey: 'price',
        header: t('fields.price'),
        meta: { align: 'right' },
        cell: ({ row }) => <MoneyText value={row.original.price} currency={currency} />,
      },
      { accessorKey: 'charge_type', header: t('extras.chargeType'), cell: ({ row }) => t(`extras.chargeTypes.${row.original.charge_type}`) },
      {
        id: 'tax',
        header: t('extras.tax'),
        cell: ({ row }) => (row.original.tax ? (taxNames.get(row.original.tax) ?? '—') : t('extras.noTax')),
      },
      {
        id: 'flags',
        header: t('taxes.rules'),
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1.5">
            {row.original.sellable_online && <Badge tone="info">{t('extras.online')}</Badge>}
            {!row.original.is_active && <Badge tone="stone">{t('states.inactive')}</Badge>}
          </div>
        ),
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
              toast.success(t('extras.deleted'))
            }}
          />
        ),
      },
    ],
    [t, lang, currency, taxNames, canManage, editor, remove],
  )

  return (
    <div>
      <PageHeader
        title={t('extras.title')}
        description={t('extras.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={editor.create}>
              <Plus aria-hidden />
              {t('extras.new')}
            </Button>
          )
        }
      />
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('extras.title')}
          columns={columns}
          data={query.data ?? []}
          isLoading={query.isPending}
          getRowId={(row) => row.id}
          empty={<EmptyState icon={Coffee} title={t('extras.empty')} description={t('extras.emptyHint')} />}
        />
      )}
      <ExtraDialog
        key={editor.key}
        open={editor.open}
        extra={editor.item}
        taxes={taxes.data ?? []}
        currency={currency}
        onOpenChange={editor.setOpen}
      />
    </div>
  )
}

function ExtraDialog({
  open,
  extra,
  taxes,
  currency,
  onOpenChange,
}: {
  open: boolean
  extra: Extra | null
  taxes: Tax[]
  currency: string
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation('rates')
  const save = useSaveResource<Extra>('extras')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(extra) })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null
  const taxOptions = [
    { value: NO_TAX, label: t('extras.noTax') },
    ...taxes
      .filter((tax) => tax.applies_to !== 'room' && (tax.is_active || tax.id === extra?.tax))
      .map((tax) => ({ value: tax.id, label: tax.name })),
  ]

  const submit = form.handleSubmit(async (values) => {
    const body = {
      code: values.code,
      name: toI18n(values.name_es, values.name_en),
      price: values.price,
      charge_type: values.charge_type,
      tax: values.tax === NO_TAX ? null : values.tax,
      sellable_online: values.sellable_online,
      is_active: values.is_active,
    }
    try {
      await save.mutateAsync(extra ? { ...body, id: extra.id } : body)
      toast.success(t(extra ? 'extras.updated' : 'extras.created'))
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
      title={t(extra ? 'extras.edit' : 'extras.new')}
      description={t('extras.dialogHint')}
      submitLabel={t(extra ? 'crud.save' : 'extras.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
    >
      <TextField control={form.control} name="code" label={t('fields.code')} className="sm:w-48" />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField control={form.control} name="name_es" label={t('fields.nameEs')} />
        <TextField control={form.control} name="name_en" label={t('fields.nameEn')} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <MoneyField control={form.control} name="price" label={t('fields.price')} currency={currency} />
        <SelectField
          control={form.control}
          name="charge_type"
          label={t('extras.chargeType')}
          options={CHARGE_TYPES.map((value) => ({ value, label: t(`extras.chargeTypes.${value}`) }))}
        />
      </div>
      <SelectField control={form.control} name="tax" label={t('extras.tax')} options={taxOptions} />
      <SwitchField control={form.control} name="sellable_online" label={t('extras.onlineLabel')} description={t('extras.onlineHint')} />
      <SwitchField control={form.control} name="is_active" label={t('fields.active')} />
    </FormDialog>
  )
}
