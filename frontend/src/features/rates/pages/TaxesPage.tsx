import { zodResolver } from '@hookform/resolvers/zod'
import type { ColumnDef } from '@tanstack/react-table'
import { Percent, Plus } from 'lucide-react'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { DataTable } from '@/components/DataTable'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useDeleteResource, useRatesList, useSaveResource, type Tax } from '../api'
import { FormDialog, RowActions, SelectField, SwitchField, TextField } from '../components/crud'
import { useEditor } from '../hooks/useEditor'
import { fieldErrors, parseDecimal } from '../lib/forms'

const APPLIES_TO = ['room', 'extras', 'all'] as const

const schema = z.object({
  code: z.string().trim().min(1, 'validation.required').max(20),
  name: z.string().trim().min(1, 'validation.required').max(100),
  rate: z.string().refine((value) => {
    const rate = parseDecimal(value, { signed: false })
    return rate !== null && Number(rate) <= 100
  }, 'rates:taxes.rateInvalid'),
  applies_to: z.enum(APPLIES_TO),
  included_in_price: z.boolean(),
  exempt_foreign_non_residents: z.boolean(),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

const FIELD_MAP = Object.fromEntries(Object.keys(schema.shape).map((key) => [key, key]))

function toValues(tax: Tax | null): Values {
  return {
    code: tax?.code ?? '',
    name: tax?.name ?? '',
    rate: tax ? String(Number(tax.rate)) : '',
    applies_to: tax?.applies_to ?? 'room',
    included_in_price: tax?.included_in_price ?? false,
    exempt_foreign_non_residents: tax?.exempt_foreign_non_residents ?? false,
    is_active: tax?.is_active ?? true,
  }
}

/** `/app/settings/taxes`: VAT and other taxes applied to lodging and extras. */
export default function TaxesPage() {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const query = useRatesList<Tax>('taxes')
  const remove = useDeleteResource('taxes')
  const editor = useEditor<Tax>()

  const columns = useMemo<ColumnDef<Tax>[]>(
    () => [
      { accessorKey: 'code', header: t('fields.code'), cell: ({ row }) => <span className="font-semibold">{row.original.code}</span> },
      { accessorKey: 'name', header: t('fields.name') },
      {
        accessorKey: 'rate',
        header: t('taxes.rate'),
        meta: { align: 'right' },
        cell: ({ row }) => `${formatNumber(Number(row.original.rate), lang)} %`,
      },
      { accessorKey: 'applies_to', header: t('taxes.appliesTo'), cell: ({ row }) => t(`taxes.scopes.${row.original.applies_to}`) },
      {
        id: 'flags',
        header: t('taxes.rules'),
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1.5">
            <Badge tone={row.original.included_in_price ? 'info' : 'neutral'}>
              {t(row.original.included_in_price ? 'taxes.included' : 'taxes.excluded')}
            </Badge>
            {row.original.exempt_foreign_non_residents && <Badge tone="success">{t('taxes.exemptBadge')}</Badge>}
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
            name={row.original.name}
            canEdit={canManage}
            onEdit={() => editor.edit(row.original)}
            onDelete={async () => {
              await remove.mutateAsync(row.original.id)
              toast.success(t('taxes.deleted'))
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
        title={t('taxes.title')}
        description={t('taxes.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={editor.create}>
              <Plus aria-hidden />
              {t('taxes.new')}
            </Button>
          )
        }
      />
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('taxes.title')}
          columns={columns}
          data={query.data ?? []}
          isLoading={query.isPending}
          getRowId={(row) => row.id}
          empty={<EmptyState icon={Percent} title={t('taxes.empty')} description={t('taxes.emptyHint')} />}
        />
      )}
      <TaxDialog key={editor.key} open={editor.open} tax={editor.item} onOpenChange={editor.setOpen} />
    </div>
  )
}

function TaxDialog({ open, tax, onOpenChange }: { open: boolean; tax: Tax | null; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation('rates')
  const save = useSaveResource<Tax>('taxes')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(tax) })
  const general = save.isError ? fieldErrors(save.error, FIELD_MAP).general : null

  const submit = form.handleSubmit(async (values) => {
    const body = { ...values, rate: parseDecimal(values.rate, { signed: false }) ?? values.rate }
    try {
      await save.mutateAsync(tax ? { ...body, id: tax.id } : body)
      toast.success(t(tax ? 'taxes.updated' : 'taxes.created'))
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
      title={t(tax ? 'taxes.edit' : 'taxes.new')}
      description={t('taxes.dialogHint')}
      submitLabel={t(tax ? 'crud.save' : 'taxes.create')}
      pending={save.isPending}
      error={general}
      onSubmit={submit}
    >
      <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
        <TextField control={form.control} name="code" label={t('fields.code')} />
        <TextField control={form.control} name="name" label={t('fields.name')} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField control={form.control} name="rate" label={t('taxes.rateLabel')} inputMode="decimal" />
        <SelectField
          control={form.control}
          name="applies_to"
          label={t('taxes.appliesTo')}
          options={APPLIES_TO.map((value) => ({ value, label: t(`taxes.scopes.${value}`) }))}
        />
      </div>
      <SwitchField control={form.control} name="included_in_price" label={t('taxes.includedLabel')} description={t('taxes.includedHint')} />
      <SwitchField
        control={form.control}
        name="exempt_foreign_non_residents"
        label={t('taxes.exemptLabel')}
        description={t('taxes.exemptHint')}
      />
      <SwitchField control={form.control} name="is_active" label={t('fields.active')} />
    </FormDialog>
  )
}
