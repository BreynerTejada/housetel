import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useFieldArray, useForm, useWatch, type Path } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { COMPANY_KINDS, TAX_RESPONSIBILITIES, useSaveCompany, type Company, type CompanyInput, type CompanyKind } from '../api'
import { checkDigit, formatNit, MAX_NIT_DIGITS, splitNit } from '../lib/nit'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const optionalEmail = z
  .string()
  .trim()
  .refine((value) => !value || EMAIL.test(value), 'corporate:form.emailInvalid')

const schema = z
  .object({
    kind: z.enum(['corporate', 'travel_agency', 'government', 'other']),
    legal_name: z.string().trim().min(1, 'corporate:form.legalNameRequired'),
    trade_name: z.string().trim(),
    nit: z.string().trim(),
    vat_responsible: z.boolean(),
    tax_responsibilities: z.array(z.string()),
    billing_email: optionalEmail,
    phone: z.string().trim(),
    address: z.string().trim(),
    city: z.string().trim(),
    department: z.string().trim(),
    credit_enabled: z.boolean(),
    credit_limit: z.string(),
    payment_terms_days: z.string().trim().refine((value) => /^\d{1,3}$/.test(value) && Number(value) <= 365, 'corporate:form.termsInvalid'),
    contacts: z.array(
      z.object({
        name: z.string().trim().min(1, 'corporate:form.contactNameRequired'),
        role: z.string().trim(),
        email: optionalEmail,
        phone: z.string().trim(),
      }),
    ),
    notes: z.string().trim(),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    const { digits, dv } = splitNit(values.nit)
    if (digits.length < 5 || digits.length > MAX_NIT_DIGITS) {
      ctx.addIssue({ code: 'custom', path: ['nit'], message: 'corporate:form.nitInvalid' })
    } else if (dv && dv !== checkDigit(digits)) {
      ctx.addIssue({ code: 'custom', path: ['nit'], message: 'corporate:form.dvMismatch' })
    }
    if (values.credit_enabled && Number(values.payment_terms_days) < 1) {
      ctx.addIssue({ code: 'custom', path: ['payment_terms_days'], message: 'corporate:form.termsRequired' })
    }
  })
type Values = z.infer<typeof schema>

function defaults(company?: Company | null): Values {
  return {
    kind: company?.kind ?? 'corporate',
    legal_name: company?.legal_name ?? '',
    trade_name: company?.trade_name ?? '',
    nit: company ? formatNit(company.nit, company.dv) : '',
    vat_responsible: company?.vat_responsible ?? true,
    tax_responsibilities: company?.tax_responsibilities ?? [],
    billing_email: company?.billing_email ?? '',
    phone: company?.phone ?? '',
    address: company?.address ?? '',
    city: company?.city ?? '',
    department: company?.department ?? '',
    credit_enabled: company?.credit_enabled ?? false,
    credit_limit: company?.credit_limit ?? '',
    payment_terms_days: String(company?.payment_terms_days ?? 30),
    contacts: company?.contacts ?? [],
    notes: company?.notes ?? '',
    is_active: company?.is_active ?? true,
  }
}

function toPayload(values: Values): Partial<CompanyInput> {
  const { digits } = splitNit(values.nit)
  return {
    ...values,
    kind: values.kind as CompanyKind,
    nit: digits,
    dv: checkDigit(digits),
    credit_limit: values.credit_enabled && values.credit_limit ? values.credit_limit : null,
    payment_terms_days: Number(values.payment_terms_days),
    country: 'CO',
  }
}

/** Create (no `company`) or edit a corporate client. `onSaved` gets the saved company. */
export function CompanyFormDialog({
  open,
  onOpenChange,
  company,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  company?: Company | null
  onSaved?: (company: Company) => void
}) {
  const [pending, setPending] = useState(false)
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-2xl" hideClose={pending}>
        {open && (
          <CompanyForm company={company} onPendingChange={setPending} onClose={() => onOpenChange(false)} onSaved={onSaved} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function CompanyForm({
  company,
  onPendingChange,
  onClose,
  onSaved,
}: {
  company?: Company | null
  onPendingChange: (pending: boolean) => void
  onClose: () => void
  onSaved?: (company: Company) => void
}) {
  const { t } = useTranslation('corporate')
  const editing = Boolean(company)
  const save = useSaveCompany()
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults(company) })
  const { control } = form
  const contacts = useFieldArray({ control, name: 'contacts' })
  const nit = useWatch({ control, name: 'nit' })
  const creditEnabled = useWatch({ control, name: 'credit_enabled' })
  const isActive = useWatch({ control, name: 'is_active' })
  const { digits, dv } = splitNit(nit ?? '')
  const computedDv = digits.length >= 5 ? checkDigit(digits) : ''

  async function onSubmit(values: Values) {
    setFailure(null)
    onPendingChange(true)
    try {
      const saved = await save.mutateAsync({ id: company?.id, ...toPayload(values) })
      toast.success(editing ? t('form.saved') : t('form.created', { name: saved.legal_name }))
      onPendingChange(false)
      onClose()
      onSaved?.(saved)
    } catch (error) {
      onPendingChange(false)
      if (isApiError(error) && error.fields) {
        for (const [field, messages] of Object.entries(error.fields)) {
          const target = field === 'dv' ? 'nit' : field
          if (target in values) form.setError(target as Path<Values>, { message: messages[0] })
        }
      }
      setFailure(errorMessage(error, t))
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-5" noValidate>
      <DialogHeader>
        <DialogTitle>{editing ? t('form.editTitle') : t('form.createTitle')}</DialogTitle>
        <DialogDescription>{t('form.description')}</DialogDescription>
      </DialogHeader>

      <Section title={t('form.identity')}>
        <FormField
          control={control}
          name="legal_name"
          label={t('fields.legalName')}
          className="sm:col-span-2"
          render={({ field, ...a11y }) => <Input autoComplete="organization" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="nit"
          label={t('fields.nit')}
          description={
            computedDv
              ? dv && dv !== computedDv
                ? t('form.dvShouldBe', { dv: computedDv })
                : t('form.dvComputed', { nit: formatNit(digits, computedDv) })
              : t('form.nitHint')
          }
          render={({ field, ...a11y }) => <Input inputMode="numeric" autoComplete="off" placeholder="900.123.456-7" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="kind"
          label={t('fields.kind')}
          render={({ field, id, ...a11y }) => (
            <Select name={field.name} value={field.value} onValueChange={field.onChange}>
              <SelectTrigger id={id} {...a11y}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {COMPANY_KINDS.map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {t(`kinds.${kind}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        <FormField
          control={control}
          name="trade_name"
          label={t('fields.tradeName')}
          className="sm:col-span-2"
          render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
        />
      </Section>

      <Section title={t('form.tax')}>
        <FormField
          control={control}
          name="vat_responsible"
          label={t('fields.vatResponsible')}
          description={t('fields.vatResponsibleHint')}
          className="sm:col-span-2"
          render={({ field, id, ...a11y }) => (
            <Switch id={id} checked={field.value} onCheckedChange={field.onChange} {...a11y} />
          )}
        />
        <FormField
          control={control}
          name="tax_responsibilities"
          label={t('fields.responsibilities')}
          description={t('fields.responsibilitiesHint')}
          className="sm:col-span-2"
          render={({ field, id }) => (
            <div id={id} role="group" className="flex flex-wrap gap-2">
              {TAX_RESPONSIBILITIES.map((code) => {
                const checked = field.value.includes(code)
                return (
                  <label
                    key={code}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-[13px] transition-colors',
                      checked ? 'border-accent/40 bg-accent-soft text-accent-ink' : 'border-border hover:border-border-strong',
                    )}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(value) =>
                        field.onChange(value === true ? [...field.value, code] : field.value.filter((item) => item !== code))
                      }
                    />
                    <span className="num font-semibold">{code}</span>
                    <span className="text-muted">{t(`responsibilities.${code}`)}</span>
                  </label>
                )
              })}
            </div>
          )}
        />
      </Section>

      <Section title={t('form.billingContact')}>
        <FormField
          control={control}
          name="billing_email"
          label={t('fields.billingEmail')}
          description={t('fields.billingEmailHint')}
          render={({ field, ...a11y }) => <Input type="email" autoComplete="off" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="phone"
          label={t('fields.phone')}
          render={({ field, ...a11y }) => <Input type="tel" autoComplete="off" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="address"
          label={t('fields.address')}
          className="sm:col-span-2"
          render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="city"
          label={t('fields.city')}
          render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
        />
        <FormField
          control={control}
          name="department"
          label={t('fields.department')}
          render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
        />
      </Section>

      <Section title={t('form.credit')}>
        <FormField
          control={control}
          name="credit_enabled"
          label={t('fields.creditEnabled')}
          description={t('fields.creditEnabledHint')}
          className="sm:col-span-2"
          render={({ field, id, ...a11y }) => <Switch id={id} checked={field.value} onCheckedChange={field.onChange} {...a11y} />}
        />
        {creditEnabled && (
          <>
            <FormField
              control={control}
              name="credit_limit"
              label={t('fields.creditLimit')}
              description={t('fields.creditLimitHint')}
              render={({ field, ...a11y }) => (
                <MoneyInput value={field.value} onChange={field.onChange} onBlur={field.onBlur} name={field.name} {...a11y} />
              )}
            />
            <FormField
              control={control}
              name="payment_terms_days"
              label={t('fields.terms')}
              description={t('fields.termsHint')}
              render={({ field, ...a11y }) => (
                <Input
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={365}
                  name={field.name}
                  value={field.value}
                  onChange={(event) => field.onChange(event.target.value)}
                  onBlur={field.onBlur}
                  {...a11y}
                />
              )}
            />
          </>
        )}
      </Section>

      <fieldset className="grid min-w-0 gap-3">
        <legend className="eyebrow mb-1">{t('form.contacts')}</legend>
        {contacts.fields.length === 0 && <p className="text-[13px] text-muted">{t('form.noContacts')}</p>}
        {contacts.fields.map((contact, index) => (
          <div key={contact.id} className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-[1fr_1fr_auto]">
            <FormField
              control={control}
              name={`contacts.${index}.name`}
              label={t('fields.contactName')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
            />
            <FormField
              control={control}
              name={`contacts.${index}.role`}
              label={t('fields.contactRole')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />}
            />
            <div className="flex items-end justify-end sm:row-span-2">
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('form.removeContact', { name: contact.name || index + 1 })}
                onClick={() => contacts.remove(index)}
              >
                <Trash2 aria-hidden />
              </Button>
            </div>
            <FormField
              control={control}
              name={`contacts.${index}.email`}
              label={t('fields.contactEmail')}
              render={({ field, ...a11y }) => <Input type="email" autoComplete="off" {...field} {...a11y} />}
            />
            <FormField
              control={control}
              name={`contacts.${index}.phone`}
              label={t('fields.contactPhone')}
              render={({ field, ...a11y }) => <Input type="tel" autoComplete="off" {...field} {...a11y} />}
            />
          </div>
        ))}
        <Button
          variant="secondary"
          size="sm"
          className="w-fit"
          onClick={() => contacts.append({ name: '', role: '', email: '', phone: '' })}
        >
          <Plus aria-hidden />
          {t('form.addContact')}
        </Button>
      </fieldset>

      <FormField
        control={control}
        name="notes"
        label={t('fields.notes')}
        render={({ field, ...a11y }) => <Textarea rows={2} {...field} {...a11y} />}
      />

      {editing && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
          <div>
            <Label htmlFor="company-active">{t('fields.active')}</Label>
            <p className="text-xs text-muted">{t('fields.activeHint')}</p>
          </div>
          <Switch
            id="company-active"
            checked={isActive}
            onCheckedChange={(value) => form.setValue('is_active', value, { shouldDirty: true })}
          />
        </div>
      )}

      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}

      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={save.isPending}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          {editing ? t('common:actions.saveChanges') : t('form.create')}
        </Button>
      </DialogFooter>
    </form>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="grid min-w-0 grid-cols-1 items-start gap-4 sm:grid-cols-2">
      <legend className="eyebrow mb-1 sm:col-span-2">{title}</legend>
      {children}
    </fieldset>
  )
}
