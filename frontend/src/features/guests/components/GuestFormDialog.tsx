import { zodResolver } from '@hookform/resolvers/zod'
import { useState, type ReactNode } from 'react'
import { useForm, useWatch, type Path, type UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { DatePicker } from '@/components/DatePicker'
import { FormField } from '@/components/FormField'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useActiveProperty } from '@/lib/auth'
import {
  DOCUMENT_TYPES,
  useCreateGuest,
  useGuestLookup,
  useUpdateGuest,
  type Guest,
  type GuestPayload,
} from '../api'
import { formatDocument } from '../format'
import { useDebouncedValue } from '../hooks'
import { CountrySelect } from './CountrySelect'
import { GuestAvatar } from './GuestAvatar'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const NONE = 'none'

const schema = z.object({
  first_name: z.string().trim().min(1, 'guests:fields.firstNameRequired'),
  last_name: z.string().trim(),
  document_type: z.string(),
  document_number: z.string().trim(),
  birth_date: z.string().nullable(),
  gender: z.string(),
  email: z
    .string()
    .trim()
    .refine((value) => !value || EMAIL.test(value), 'guests:fields.emailInvalid'),
  phone: z.string().trim(),
  language: z.string(),
  nationality: z.string(),
  country_of_residence: z.string(),
  city_of_residence: z.string().trim(),
  address: z.string().trim(),
  is_vip: z.boolean(),
  blacklisted: z.boolean(),
  marketing_consent: z.boolean(),
  data_processing_consent: z.boolean(),
})
type Values = z.infer<typeof schema>

function defaults(guest?: Guest | null): Values {
  return {
    first_name: guest?.first_name ?? '',
    last_name: guest?.last_name ?? '',
    document_type: guest?.document_type || 'CC',
    document_number: guest?.document_number ?? '',
    birth_date: guest?.birth_date ?? null,
    gender: guest?.gender || NONE,
    email: guest?.email ?? '',
    phone: guest?.phone ?? '',
    language: guest?.language || 'es',
    nationality: guest?.nationality ?? 'CO',
    country_of_residence: guest?.country_of_residence ?? 'CO',
    city_of_residence: guest?.city_of_residence ?? '',
    address: guest?.address ?? '',
    is_vip: guest?.is_vip ?? false,
    blacklisted: guest?.blacklisted ?? false,
    marketing_consent: guest?.marketing_consent ?? false,
    data_processing_consent: Boolean(guest?.data_processing_consent_at),
  }
}

function toPayload(values: Values, dirty: Partial<Record<keyof Values, unknown>>, editing: boolean): GuestPayload {
  const payload: GuestPayload = {
    ...values,
    document_type: values.document_number ? (values.document_type as GuestPayload['document_type']) : '',
    gender: values.gender === NONE ? '' : (values.gender as GuestPayload['gender']),
  }
  // Consent is a moment in time: only send it when the user changed it (true records now, false revokes).
  if (editing && !dirty.data_processing_consent) delete payload.data_processing_consent
  return payload
}

/** Create (no `guest`) or edit a guest. Calls `onSaved` with the saved guest. */
export function GuestFormDialog({
  open,
  onOpenChange,
  guest,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  guest?: Guest | null
  onSaved?: (guest: Guest) => void
}) {
  const [pending, setPending] = useState(false)
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-2xl" hideClose={pending}>
        {/* Mounted on every opening: the form starts from the guest (or empty) each time. */}
        <GuestForm guest={guest} onPendingChange={setPending} onClose={() => onOpenChange(false)} onSaved={onSaved} />
      </DialogContent>
    </Dialog>
  )
}

function GuestForm({
  guest,
  onPendingChange,
  onClose,
  onSaved,
}: {
  guest?: Guest | null
  onPendingChange: (pending: boolean) => void
  onClose: () => void
  onSaved?: (guest: Guest) => void
}) {
  const { t } = useTranslation('guests')
  const editing = Boolean(guest)
  const navigate = useNavigate()
  const { property } = useActiveProperty()
  const create = useCreateGuest()
  const update = useUpdateGuest(guest?.id ?? '')
  const [failure, setFailure] = useState<string | null>(null)
  const [existingId, setExistingId] = useState<string | null>(null)
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults(guest) })
  const { control } = form

  const watched = useWatch({ control })
  const lookup = useGuestLookup(useDebouncedValue(editing ? null : watched, 450) as Parameters<typeof useGuestLookup>[0])
  const matches = editing ? [] : (lookup.data ?? []).slice(0, 3)

  async function onSubmit(values: Values) {
    setFailure(null)
    setExistingId(null)
    const payload = toPayload(values, form.formState.dirtyFields, editing)
    onPendingChange(true)
    try {
      const saved = editing ? await update.mutateAsync(payload) : await create.mutateAsync(payload)
      toast.success(editing ? t('form.saved') : t('form.created'))
      onPendingChange(false)
      onClose()
      onSaved?.(saved)
    } catch (error) {
      onPendingChange(false)
      if (isApiError(error) && error.code === 'guest_exists' && typeof error.data?.guest_id === 'string') {
        setExistingId(error.data.guest_id)
        setFailure(t('form.exists'))
        return
      }
      if (isApiError(error) && error.fields) {
        for (const [field, messages] of Object.entries(error.fields)) {
          if (field in values) form.setError(field as Path<Values>, { message: messages[0] })
        }
      }
      setFailure(errorMessage(error, t))
    }
  }

  const nationality = useWatch({ control, name: 'nationality' })

  function onNationality(value: string, previous: string) {
    form.setValue('nationality', value, { shouldDirty: true })
    const documentType = form.getValues('document_type')
    if (value && value !== 'CO' && documentType === 'CC') form.setValue('document_type', 'PA', { shouldDirty: true })
    if (value === 'CO' && documentType === 'PA') form.setValue('document_type', 'CC', { shouldDirty: true })
    const residence = form.getValues('country_of_residence')
    if (!residence || residence === previous) form.setValue('country_of_residence', value, { shouldDirty: true })
  }

  const pending = create.isPending || update.isPending

  return (
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-5" noValidate>
          <DialogHeader>
            <DialogTitle>{editing ? t('form.editTitle') : t('form.createTitle')}</DialogTitle>
            <DialogDescription>{t('form.description')}</DialogDescription>
          </DialogHeader>

          <Section title={t('form.identity')}>
            <FormField control={control} name="first_name" label={t('fields.firstName')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />} />
            <FormField control={control} name="last_name" label={t('fields.lastName')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />} />
            <FormField control={control} name="document_type" label={t('fields.documentType')}
              render={({ field, id, ...a11y }) => (
                <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} {...a11y}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DOCUMENT_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>{t(`documentTypes.${type}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            <FormField control={control} name="document_number" label={t('fields.documentNumber')}
              render={({ field, ...a11y }) => <Input autoComplete="off" className="num" {...field} {...a11y} />} />
            <FormField control={control} name="birth_date" label={t('fields.birthDate')}
              render={({ field, id, ...a11y }) => (
                <DatePicker id={id} value={field.value} onChange={field.onChange} max={property?.business_date}
                  aria-invalid={a11y['aria-invalid']} />
              )} />
            <FormField control={control} name="gender" label={t('fields.gender')}
              render={({ field, id, ...a11y }) => (
                <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} {...a11y}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[NONE, 'F', 'M', 'X'].map((gender) => (
                      <SelectItem key={gender} value={gender}>{t(`genders.${gender}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
          </Section>

          <Section title={t('form.contact')}>
            <FormField control={control} name="email" label={t('fields.email')}
              render={({ field, ...a11y }) => <Input type="email" inputMode="email" autoComplete="off" {...field} {...a11y} />} />
            <FormField control={control} name="phone" label={t('fields.phone')} description={t('fields.phoneHint')}
              render={({ field, ...a11y }) => <Input type="tel" inputMode="tel" autoComplete="off" {...field} {...a11y} />} />
            <FormField control={control} name="language" label={t('fields.language')}
              render={({ field, id, ...a11y }) => (
                <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} {...a11y}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="es">{t('languages.es', { ns: 'common' })}</SelectItem>
                    <SelectItem value="en">{t('languages.en', { ns: 'common' })}</SelectItem>
                  </SelectContent>
                </Select>
              )} />
          </Section>

          <Section title={t('form.origin')}>
            <FormField control={control} name="nationality" label={t('fields.nationality')}
              render={({ field, id, ...a11y }) => (
                <CountrySelect id={id} value={field.value} onChange={(value) => onNationality(value, nationality)}
                  aria-invalid={a11y['aria-invalid']} />
              )} />
            <FormField control={control} name="country_of_residence" label={t('fields.residence')}
              render={({ field, id, ...a11y }) => (
                <CountrySelect id={id} value={field.value} onChange={field.onChange} aria-invalid={a11y['aria-invalid']} />
              )} />
            <FormField control={control} name="city_of_residence" label={t('fields.city')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />} />
            <FormField control={control} name="address" label={t('fields.address')}
              render={({ field, ...a11y }) => <Input autoComplete="off" {...field} {...a11y} />} />
          </Section>

          <fieldset className="grid gap-3">
            <legend className="eyebrow mb-3">{t('form.consent')}</legend>
            <CheckRow form={form} name="data_processing_consent" label={t('form.consentLabel')} hint={t('form.consentHint')} />
            <CheckRow form={form} name="marketing_consent" label={t('form.marketingLabel')} />
            <div className="grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
              <SwitchRow form={form} name="is_vip" label={t('fields.vip')} hint={t('fields.vipHint')} />
              <SwitchRow form={form} name="blacklisted" label={t('fields.blacklisted')} hint={t('fields.blacklistedHint')} />
            </div>
          </fieldset>

          {matches.length > 0 && (
            <div role="status" className="grid gap-2 rounded-lg border border-warning/30 bg-warning-soft/60 p-3">
              <p className="text-[13px] font-bold text-warning-ink">{t('form.duplicatesTitle')}</p>
              <p className="text-xs text-warning-ink">{t('form.duplicatesHint')}</p>
              <ul className="grid gap-1.5">
                {matches.map((match) => (
                  <li key={match.id} className="flex items-center gap-3 rounded-md bg-surface/80 p-2">
                    <GuestAvatar name={match.full_name} vip={match.is_vip} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-semibold text-fg">{match.full_name}</p>
                      <p className="truncate text-xs text-muted">
                        {[formatDocument(match.document_type, match.document_number), match.email].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    <span className="hidden flex-wrap gap-1 sm:flex">
                      {match.reasons.map((reason) => (
                        <Badge key={reason} tone="warning">{t(`reasons.${reason}`)}</Badge>
                      ))}
                    </span>
                    <Button size="sm" onClick={() => { onClose(); navigate(`/app/guests/${match.id}`) }}>
                      {t('form.open')}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {failure && (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              <span>{failure}</span>
              {existingId && (
                <Button size="sm" onClick={() => { onClose(); navigate(`/app/guests/${existingId}`) }}>
                  {t('form.openExisting')}
                </Button>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={onClose} disabled={pending}>
              {t('actions.cancel', { ns: 'common' })}
            </Button>
            <Button type="submit" variant="primary" loading={pending}>
              {editing ? t('form.saveChanges') : t('form.save')}
            </Button>
          </DialogFooter>
        </form>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="grid gap-3">
      <legend className="eyebrow mb-3">{title}</legend>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

type BooleanField = 'data_processing_consent' | 'marketing_consent' | 'is_vip' | 'blacklisted'

interface BooleanRowProps {
  form: UseFormReturn<Values>
  name: BooleanField
  label: string
  hint?: string
}

function CheckRow({ form, name, label, hint }: BooleanRowProps) {
  const checked = useWatch({ control: form.control, name })
  const id = `guest-form-${name}`
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={id}
        name={name}
        checked={checked}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onCheckedChange={(value) => form.setValue(name, value === true, { shouldDirty: true })}
        className="mt-0.5"
      />
      <div className="grid gap-0.5">
        <Label htmlFor={id}>{label}</Label>
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-muted">
            {hint}
          </p>
        )}
      </div>
    </div>
  )
}

function SwitchRow({ form, name, label, hint }: BooleanRowProps) {
  const checked = useWatch({ control: form.control, name })
  const id = `guest-form-${name}`
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="grid gap-0.5">
        <Label htmlFor={id}>{label}</Label>
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-muted">
            {hint}
          </p>
        )}
      </div>
      <Switch
        id={id}
        name={name}
        checked={checked}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onCheckedChange={(value) => form.setValue(name, value, { shouldDirty: true })}
      />
    </div>
  )
}
