import { differenceInCalendarDays } from 'date-fns'
import { ArrowRight, Building, FlaskConical, Pencil, Plus, Plug, Trash2 } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { Controller, useForm, type Control, type FieldPath } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DatePicker } from '@/components/DatePicker'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatNumber, normalizeLang, parseDate } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  useComplianceSettings,
  useDeleteResolution,
  useResolutions,
  useSaveSettings,
  type ComplianceSettings,
  type ComplianceSettingsPayload,
  type Resolution,
  type ResolutionHealth,
} from '../api'
import { ResolutionDialog } from '../components/ResolutionDialog'
import { ResolutionHealthCard } from '../components/ResolutionHealth'

const SIRE_DOCUMENTS = ['PA', 'CE', 'DNI', 'PEP', 'PPT', 'OTHER'] as const

/** Same rules as the backend (`services/pending.resolution_health`), from the active invoice resolution. */
function healthOf(resolution: Resolution | undefined, today: string | undefined): ResolutionHealth {
  if (!resolution) return { status: 'missing', message: '' }
  const day = parseDate(today) ?? new Date()
  const total = resolution.to_number - resolution.from_number + 1
  const used = total - resolution.remaining
  const daysLeft = differenceInCalendarDays(parseDate(resolution.valid_to) ?? day, day)
  let status: ResolutionHealth['status'] = 'ok'
  if (daysLeft < 0 || resolution.remaining <= 0) status = 'critical'
  else if ((parseDate(resolution.valid_from) ?? day) > day || used / total >= 0.9 || daysLeft < 30) status = 'warning'
  return {
    status,
    message: '',
    resolution_id: resolution.id,
    prefix: resolution.prefix,
    from_number: resolution.from_number,
    to_number: resolution.to_number,
    next_number: resolution.next_number,
    remaining: resolution.remaining,
    used_percent: Math.round((used * 1000) / total) / 10,
    valid_to: resolution.valid_to,
    days_left: daysLeft,
    environment: resolution.environment,
  }
}

function Section({ title, description, children, id }: { title: string; description?: string; children: ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div>
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {title}
        </h2>
        {description && <p className="text-[13px] text-muted">{description}</p>}
      </div>
      {children}
    </section>
  )
}

type FormValues = ComplianceSettings & { country_rows: { iso: string; code: string }[] }

function TextInput({
  control,
  name,
  label,
  hint,
  placeholder,
  error,
  disabled,
  className,
}: {
  control: Control<FormValues>
  name: FieldPath<FormValues>
  label: string
  hint?: string
  placeholder?: string
  error?: string
  disabled?: boolean
  className?: string
}) {
  const id = useId()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className={cn('grid content-start gap-1.5', className)}>
          <Label htmlFor={id}>{label}</Label>
          <Input
            id={id}
            name={field.name}
            value={String(field.value ?? '')}
            onChange={field.onChange}
            onBlur={field.onBlur}
            placeholder={placeholder}
            disabled={disabled}
            aria-invalid={Boolean(error)}
            aria-describedby={hint ? `${id}-hint` : undefined}
            autoComplete="off"
          />
          {hint && (
            <p id={`${id}-hint`} className="text-xs text-muted">
              {hint}
            </p>
          )}
          {error && <p className="text-xs font-medium text-danger-ink">{error}</p>}
        </div>
      )}
    />
  )
}

function SwitchRow({
  control,
  name,
  label,
  hint,
  disabled,
}: {
  control: Control<FormValues>
  name: 'auto_issue_invoices' | 'tra_auto_register' | 'sire_second_surname_column'
  label: string
  hint?: string
  disabled?: boolean
}) {
  const id = useId()
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className="flex items-start gap-3">
          <Switch id={id} name={field.name} checked={field.value} onCheckedChange={field.onChange} disabled={disabled} className="mt-0.5" />
          <div className="grid gap-0.5">
            <Label htmlFor={id}>{label}</Label>
            {hint && <p className="text-xs text-muted">{hint}</p>}
          </div>
        </div>
      )}
    />
  )
}

function toFormValues(data: ComplianceSettingsPayload): FormValues {
  return {
    go_live_date: data.go_live_date,
    auto_issue_invoices: data.auto_issue_invoices,
    final_consumer_id: data.final_consumer_id,
    invoice_notes: data.invoice_notes,
    sire_establishment_code: data.sire_establishment_code,
    sire_city_code: data.sire_city_code,
    // every known type has a value ('' = default code) so the form does not start dirty
    sire_document_codes: { ...Object.fromEntries(SIRE_DOCUMENTS.map((code) => [code, ''])), ...data.sire_document_codes },
    sire_country_codes: { ...data.sire_country_codes },
    sire_second_surname_column: data.sire_second_surname_column,
    tra_auto_register: data.tra_auto_register,
    tra_establishment_id: data.tra_establishment_id,
    tra_travel_reason: data.tra_travel_reason,
    tra_accommodation_type: data.tra_accommodation_type,
    country_rows: Object.entries(data.sire_country_codes).map(([iso, code]) => ({ iso, code })),
  }
}

function SettingsForm({ data, canEdit }: { data: ComplianceSettingsPayload; canEdit: boolean }) {
  const { t } = useTranslation('compliance')
  const save = useSaveSettings()
  const form = useForm<FormValues>({ defaultValues: toFormValues(data) })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const rows = form.watch('country_rows')
  const travelReasons = Object.values(data.defaults.travel_reasons)

  const submit = form.handleSubmit(async ({ country_rows, ...values }) => {
    setErrors({})
    const documents = Object.fromEntries(Object.entries(values.sire_document_codes).filter(([, code]) => String(code ?? '').trim()))
    const countries = Object.fromEntries(
      country_rows.filter((row) => row.iso.trim() && row.code.trim()).map((row) => [row.iso.trim().toUpperCase(), row.code.trim()]),
    )
    try {
      const saved = await save.mutateAsync({ ...values, sire_document_codes: documents, sire_country_codes: countries })
      form.reset(toFormValues(saved))
      toast.success(t('settings.saved'))
    } catch (error) {
      if (isApiError(error) && error.fields) {
        setErrors(Object.fromEntries(Object.entries(error.fields).map(([field, messages]) => [field, messages[0] ?? ''])))
      }
      toast.error(errorMessage(error, t))
    }
  })

  return (
    <form onSubmit={submit} noValidate className="grid gap-5">
      <Section id="settings-dian" title={t('settings.dian')} description={t('settings.dianHint')}>
        <SwitchRow control={form.control} name="auto_issue_invoices" label={t('settings.autoIssue')} hint={t('settings.autoIssueHint')} disabled={!canEdit} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput
            control={form.control}
            name="final_consumer_id"
            label={t('settings.finalConsumer')}
            hint={t('settings.finalConsumerHint')}
            error={errors.final_consumer_id}
            disabled={!canEdit}
          />
          <Controller
            control={form.control}
            name="go_live_date"
            render={({ field }) => (
              <div className="grid content-start gap-1.5">
                <Label htmlFor="go-live">{t('settings.goLive')}</Label>
                <DatePicker id="go-live" value={field.value} onChange={field.onChange} disabled={!canEdit} placeholder={t('settings.goLiveNone')} />
                <p className="text-xs text-muted">{t('settings.goLiveHint')}</p>
              </div>
            )}
          />
        </div>
        <Controller
          control={form.control}
          name="invoice_notes"
          render={({ field }) => (
            <div className="grid gap-1.5">
              <Label htmlFor="invoice-notes">{t('settings.notes')}</Label>
              <Textarea id="invoice-notes" name={field.name} rows={2} value={field.value} onChange={field.onChange} disabled={!canEdit} />
              <p className="text-xs text-muted">{t('settings.notesHint')}</p>
            </div>
          )}
        />
      </Section>

      <Section id="settings-sire" title={t('settings.sire')} description={t('settings.sireHint')}>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput
            control={form.control}
            name="sire_establishment_code"
            label={t('settings.sireCode')}
            hint={t('settings.sireCodeHint')}
            error={errors.sire_establishment_code}
            disabled={!canEdit}
          />
          <TextInput
            control={form.control}
            name="sire_city_code"
            label={t('settings.sireCity')}
            hint={t('settings.sireCityHint', { code: data.effective.sire_city_code || '—' })}
            placeholder={data.effective.sire_city_code}
            error={errors.sire_city_code}
            disabled={!canEdit}
          />
        </div>
        <SwitchRow
          control={form.control}
          name="sire_second_surname_column"
          label={t('settings.secondSurname')}
          hint={t('settings.secondSurnameHint')}
          disabled={!canEdit}
        />
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-[13px] font-semibold text-fg">{t('settings.documentCodes')}</legend>
          <p className="text-xs text-muted">{t('settings.documentCodesHint')}</p>
          <div className="grid grid-cols-2 items-end gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {SIRE_DOCUMENTS.map((code) => (
              <TextInput
                key={code}
                control={form.control}
                name={`sire_document_codes.${code}` as FieldPath<FormValues>}
                label={t(`documentTypes.${code}`)}
                placeholder={data.defaults.sire_document_codes[code] ?? ''}
                disabled={!canEdit}
              />
            ))}
          </div>
          {errors.sire_document_codes && <p className="text-xs font-medium text-danger-ink">{errors.sire_document_codes}</p>}
        </fieldset>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-[13px] font-semibold text-fg">{t('settings.countryCodes')}</legend>
          <p className="text-xs text-muted">{t('settings.countryCodesHint')}</p>
          {rows.length > 0 && (
            <ul className="grid gap-2">
              {rows.map((row, index) => (
                <li key={index} className="flex items-end gap-2">
                  <TextInput
                    control={form.control}
                    name={`country_rows.${index}.iso` as FieldPath<FormValues>}
                    label={t('settings.countryIso')}
                    placeholder="US"
                    className="w-28"
                    disabled={!canEdit}
                  />
                  <TextInput
                    control={form.control}
                    name={`country_rows.${index}.code` as FieldPath<FormValues>}
                    label={t('settings.countrySire')}
                    placeholder={data.defaults.sire_country_codes[row.iso.toUpperCase()] ?? '249'}
                    className="w-36"
                    disabled={!canEdit}
                  />
                  {canEdit && (
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('settings.removeCountry', { iso: row.iso || '—' })}
                      onClick={() => form.setValue('country_rows', rows.filter((_, i) => i !== index), { shouldDirty: true })}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {canEdit && (
            <Button
              size="sm"
              variant="ghost"
              className="w-fit"
              onClick={() => form.setValue('country_rows', [...rows, { iso: '', code: '' }], { shouldDirty: true })}
            >
              <Plus aria-hidden />
              {t('settings.addCountry')}
            </Button>
          )}
          {errors.sire_country_codes && <p className="text-xs font-medium text-danger-ink">{errors.sire_country_codes}</p>}
        </fieldset>
      </Section>

      <Section id="settings-tra" title={t('settings.tra')} description={t('settings.traHint')}>
        <SwitchRow control={form.control} name="tra_auto_register" label={t('settings.traAuto')} hint={t('settings.traAutoHint')} disabled={!canEdit} />
        <div className="grid gap-4 sm:grid-cols-3">
          <TextInput
            control={form.control}
            name="tra_establishment_id"
            label={t('settings.traRnt')}
            hint={t('settings.traRntHint', { rnt: data.effective.tra_establishment_id || '—' })}
            placeholder={data.effective.tra_establishment_id}
            error={errors.tra_establishment_id}
            disabled={!canEdit}
          />
          <Controller
            control={form.control}
            name="tra_travel_reason"
            render={({ field }) => (
              <div className="grid content-start gap-1.5">
                <Label htmlFor="tra-reason">{t('settings.traReason')}</Label>
                <Select name={field.name} value={field.value} onValueChange={field.onChange} disabled={!canEdit}>
                  <SelectTrigger id="tra-reason">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[...new Set([field.value, ...travelReasons])].filter(Boolean).map((reason) => (
                      <SelectItem key={reason} value={reason}>
                        {reason}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted">{t('settings.traReasonHint')}</p>
              </div>
            )}
          />
          <TextInput
            control={form.control}
            name="tra_accommodation_type"
            label={t('settings.traType')}
            hint={t('settings.traTypeHint', { type: data.effective.tra_accommodation_type })}
            placeholder={data.effective.tra_accommodation_type}
            disabled={!canEdit}
          />
        </div>
      </Section>

      {canEdit && (
        <div className="sticky bottom-0 z-10 -mx-1 flex justify-end gap-2 border-t border-border bg-bg/90 px-1 py-3 backdrop-blur">
          <Button onClick={() => form.reset(toFormValues(data))} disabled={!form.formState.isDirty || save.isPending}>
            {t('common:actions.cancel')}
          </Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!form.formState.isDirty}>
            {t('common:actions.saveChanges')}
          </Button>
        </div>
      )}
    </form>
  )
}

/** `/app/settings/compliance`: DIAN numbering resolution, invoicing rules, SIRE and TRA codes, integration modes. */
export default function ComplianceSettingsPage() {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const canEdit = useCan('compliance.settings')
  const settings = useComplianceSettings()
  const resolutions = useResolutions()
  const remove = useDeleteResolution()
  const [editing, setEditing] = useState<{ open: boolean; resolution: Resolution | null; key: number }>({
    open: false,
    resolution: null,
    key: 0,
  })
  const [deleting, setDeleting] = useState<Resolution | null>(null)
  const active = useMemo(
    () => resolutions.data?.find((item) => item.is_active && item.document_kind === 'invoice'),
    [resolutions.data],
  )
  const health = healthOf(active, property?.business_date)

  if (settings.isPending) return <LoadingState variant="rows" rows={8} />
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
  const data = settings.data

  return (
    <div className="grid grid-cols-1 gap-5">
      <PageHeader title={t('settings.title')} description={t('settings.description')} className="pb-1" />

      {data.supplier.missing.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/50 bg-warning-soft px-4 py-3 text-[13px] text-warning-ink">
          <p>
            {t('settings.supplierMissing', {
              fields: data.supplier.missing.map((field) => t(`settings.supplierFields.${field}`)).join(', '),
            })}
          </p>
          <Link to="/app/settings/property" className="inline-flex items-center gap-1 font-semibold underline">
            {t('settings.completeProfile')}
            <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Section
          id="settings-resolution"
          title={t('resolutions.title')}
          description={t('resolutions.description')}
        >
          <ResolutionHealthCard health={health} />
          {resolutions.isError ? (
            <ErrorState error={resolutions.error} onRetry={() => void resolutions.refetch()} className="py-6" />
          ) : (
            <ul className="grid divide-y divide-border rounded-lg border border-border">
              {(resolutions.data ?? []).map((resolution) => (
                <li key={resolution.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
                  <div className="grid gap-0.5">
                    <p className="flex flex-wrap items-center gap-2 text-[13px]">
                      <span className="num font-semibold text-fg">
                        {resolution.prefix || '—'} {formatNumber(resolution.from_number, lang)}–{formatNumber(resolution.to_number, lang)}
                      </span>
                      <Badge tone={resolution.is_active ? 'success' : 'stone'}>
                        {t(resolution.is_active ? 'resolutions.active' : 'resolutions.inactive')}
                      </Badge>
                      <Badge tone="outline">{t(`invoice.kinds.${resolution.document_kind}`)}</Badge>
                    </p>
                    <p className="num text-xs text-muted">
                      {t('resolutions.summary', {
                        number: resolution.resolution_number || '—',
                        from: formatDate(resolution.valid_from, undefined, lang),
                        to: formatDate(resolution.valid_to, undefined, lang),
                        used: resolution.invoices_count,
                      })}
                    </p>
                  </div>
                  {canEdit && (
                    <div className="flex gap-1">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t('resolutions.editOne', { prefix: resolution.prefix })}
                        onClick={() => setEditing((current) => ({ open: true, resolution, key: current.key + 1 }))}
                      >
                        <Pencil aria-hidden />
                      </Button>
                      {resolution.invoices_count === 0 && (
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={t('resolutions.deleteOne', { prefix: resolution.prefix })}
                          onClick={() => setDeleting(resolution)}
                        >
                          <Trash2 aria-hidden />
                        </Button>
                      )}
                    </div>
                  )}
                </li>
              ))}
              {resolutions.data?.length === 0 && <li className="px-3 py-4 text-[13px] text-muted">{t('resolutions.empty')}</li>}
            </ul>
          )}
          {canEdit && (
            <Button
              variant={active ? 'secondary' : 'primary'}
              className="w-fit"
              onClick={() => setEditing((current) => ({ open: true, resolution: null, key: current.key + 1 }))}
            >
              <Plus aria-hidden />
              {t('resolutions.new')}
            </Button>
          )}
        </Section>

        <div className="grid content-start gap-5">
          <Section id="settings-supplier" title={t('settings.supplier')}>
            <dl className="grid gap-2 text-[13px]">
              {(
                [
                  ['legal_name', data.supplier.legal_name],
                  ['nit', data.supplier.nit],
                  ['rnt', data.supplier.rnt],
                  ['city', data.supplier.city],
                ] as const
              ).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3">
                  <dt className="text-muted">{t(`settings.supplierFields.${key}`)}</dt>
                  <dd className="num text-right font-semibold text-fg">{value || '—'}</dd>
                </div>
              ))}
            </dl>
            <Link to="/app/settings/property" className="inline-flex w-fit items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
              <Building aria-hidden className="size-3.5" />
              {t('settings.editProfile')}
            </Link>
          </Section>
          <Section id="settings-modes" title={t('settings.modes')} description={t('settings.modesHint')}>
            <ul className="grid gap-3">
              {(['einvoice', 'sire', 'tra'] as const).map((kind) => {
                const integration = data.integrations[kind]
                return (
                  <li key={kind} className="grid gap-0.5">
                    <p className="flex flex-wrap items-center justify-between gap-2 text-[13px] font-semibold text-fg">
                      {t(`settings.integration.${kind}`)}
                      <Badge tone={integration.mode === 'real' ? 'info' : 'outline'}>
                        {integration.mode === 'simulated' && <FlaskConical aria-hidden />}
                        {t(`mode.${integration.mode}`)}
                      </Badge>
                    </p>
                    <p className="text-xs text-muted">{integration.provider_label}</p>
                  </li>
                )
              })}
            </ul>
            <Link to="/app/settings/integrations" className="inline-flex w-fit items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
              <Plug aria-hidden className="size-3.5" />
              {t('settings.changeModes')}
            </Link>
          </Section>
        </div>
      </div>

      <SettingsForm data={data} canEdit={canEdit} />

      <ResolutionDialog
        key={editing.key}
        open={editing.open}
        resolution={editing.resolution}
        onOpenChange={(open) => setEditing((current) => ({ ...current, open }))}
      />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('resolutions.deleteTitle', { prefix: deleting?.prefix ?? '' })}
        description={t('resolutions.deleteHint')}
        confirmLabel={t('common:actions.delete')}
        onConfirm={async () => {
          if (!deleting) return
          await remove.mutateAsync(deleting.id)
          toast.success(t('resolutions.deleted'))
        }}
      />
    </div>
  )
}
