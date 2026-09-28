import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { DatePicker } from '@/components/DatePicker'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useSaveResolution, type Resolution } from '../api'

const schema = z
  .object({
    document_kind: z.enum(['invoice', 'credit_note']),
    prefix: z.string().trim().max(10).regex(/^[A-Za-z0-9]*$/, 'compliance:resolutions.form.prefixInvalid'),
    resolution_number: z.string().trim().max(40),
    from_number: z.string().regex(/^\d+$/, 'validation.number'),
    to_number: z.string().regex(/^\d+$/, 'validation.number'),
    valid_from: z.string().min(1, 'validation.required'),
    valid_to: z.string().min(1, 'validation.required'),
    technical_key: z.string().trim().max(128),
    environment: z.enum(['test', 'production']),
    provider_range_id: z.string().trim().max(40),
    is_active: z.boolean(),
  })
  .refine((values) => Number(values.to_number) >= Number(values.from_number), {
    path: ['to_number'],
    message: 'compliance:resolutions.form.rangeInvalid',
  })
  .refine((values) => !values.valid_from || !values.valid_to || values.valid_to >= values.valid_from, {
    path: ['valid_to'],
    message: 'compliance:resolutions.form.datesInvalid',
  })
type Values = z.infer<typeof schema>

function toValues(resolution: Resolution | null): Values {
  return {
    document_kind: resolution?.document_kind ?? 'invoice',
    prefix: resolution?.prefix ?? '',
    resolution_number: resolution?.resolution_number ?? '',
    from_number: String(resolution?.from_number ?? 1),
    to_number: String(resolution?.to_number ?? ''),
    valid_from: resolution?.valid_from ?? '',
    valid_to: resolution?.valid_to ?? '',
    technical_key: resolution?.technical_key ?? '',
    environment: resolution?.environment ?? 'test',
    provider_range_id: resolution?.provider_range_id ?? '',
    is_active: resolution?.is_active ?? true,
  }
}

/** Create or edit a DIAN numbering resolution (prefix, range, validity, technical key). */
export function ResolutionDialog({
  open,
  resolution,
  onOpenChange,
}: {
  open: boolean
  resolution: Resolution | null
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation('compliance')
  const save = useSaveResolution()
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(resolution) })
  const used = (resolution?.invoices_count ?? 0) > 0

  const submit = form.handleSubmit(async (values) => {
    const body = { ...values, from_number: Number(values.from_number), to_number: Number(values.to_number) }
    try {
      await save.mutateAsync(resolution ? { ...body, id: resolution.id } : body)
      toast.success(t(resolution ? 'resolutions.updated' : 'resolutions.created'))
      onOpenChange(false)
    } catch (error) {
      if (isApiError(error) && error.fields) {
        for (const [field, messages] of Object.entries(error.fields)) {
          if (field in values) form.setError(field as keyof Values, { message: messages[0] })
        }
      }
      if (!isApiError(error) || !error.fields) form.setError('root', { message: errorMessage(error, t) })
    }
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !save.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-xl">
        <form onSubmit={submit} noValidate className="grid gap-5">
          <DialogHeader>
            <DialogTitle>{t(resolution ? 'resolutions.edit' : 'resolutions.new')}</DialogTitle>
            <DialogDescription>{t('resolutions.dialogHint')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="document_kind"
                label={t('resolutions.form.kind')}
                render={({ field, id, ...a11y }) => (
                  <Select name={field.name} value={field.value} onValueChange={field.onChange} disabled={used}>
                    <SelectTrigger id={id} {...a11y}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="invoice">{t('invoice.kinds.invoice')}</SelectItem>
                      <SelectItem value="credit_note">{t('invoice.kinds.credit_note')}</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
              <FormField
                control={form.control}
                name="environment"
                label={t('resolutions.form.environment')}
                render={({ field, id, ...a11y }) => (
                  <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id={id} {...a11y}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="test">{t('environment.test')}</SelectItem>
                      <SelectItem value="production">{t('environment.production')}</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
              <FormField
                control={form.control}
                name="prefix"
                label={t('resolutions.form.prefix')}
                render={({ field, ...a11y }) => <Input {...field} {...a11y} disabled={used} autoComplete="off" className="uppercase" />}
              />
              <FormField
                control={form.control}
                name="resolution_number"
                label={t('resolutions.form.number')}
                description={t('resolutions.form.numberHint')}
                render={({ field, ...a11y }) => <Input {...field} {...a11y} inputMode="numeric" autoComplete="off" />}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="from_number"
                label={t('resolutions.form.from')}
                render={({ field, ...a11y }) => <Input {...field} {...a11y} inputMode="numeric" disabled={used} autoComplete="off" />}
              />
              <FormField
                control={form.control}
                name="to_number"
                label={t('resolutions.form.to')}
                render={({ field, ...a11y }) => <Input {...field} {...a11y} inputMode="numeric" autoComplete="off" />}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="valid_from"
                label={t('resolutions.form.validFrom')}
                render={({ field, id, ...a11y }) => (
                  <DatePicker id={id} value={field.value || null} onChange={(value) => field.onChange(value ?? '')} aria-invalid={a11y['aria-invalid']} />
                )}
              />
              <FormField
                control={form.control}
                name="valid_to"
                label={t('resolutions.form.validTo')}
                render={({ field, id, ...a11y }) => (
                  <DatePicker id={id} value={field.value || null} onChange={(value) => field.onChange(value ?? '')} aria-invalid={a11y['aria-invalid']} />
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="technical_key"
              label={t('resolutions.form.technicalKey')}
              description={t('resolutions.form.technicalKeyHint')}
              render={({ field, ...a11y }) => <Input {...field} {...a11y} autoComplete="off" spellCheck={false} className="font-mono text-[13px]" />}
            />
            <FormField
              control={form.control}
              name="provider_range_id"
              label={t('resolutions.form.providerRange')}
              description={t('resolutions.form.providerRangeHint')}
              render={({ field, ...a11y }) => <Input {...field} {...a11y} inputMode="numeric" autoComplete="off" />}
            />
            <Controller
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <div className="flex items-start gap-3">
                  <Switch id="resolution-active" name={field.name} checked={field.value} onCheckedChange={field.onChange} className="mt-0.5" />
                  <div className="grid gap-0.5">
                    <Label htmlFor="resolution-active">{t('resolutions.form.active')}</Label>
                    <p className="text-xs text-muted">{t('resolutions.form.activeHint')}</p>
                  </div>
                </div>
              )}
            />
          </div>
          {form.formState.errors.root?.message && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {form.formState.errors.root.message}
            </p>
          )}
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)} disabled={save.isPending}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {t(resolution ? 'common:actions.saveChanges' : 'resolutions.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
