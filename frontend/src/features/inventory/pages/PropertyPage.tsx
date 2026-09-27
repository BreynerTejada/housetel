import { useMutation } from '@tanstack/react-query'
import { ImageUp, Trash2 } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { api, isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useAmenities, useInvalidateInventory, usePropertyProfile, type I18nText, type PropertyPolicies, type PropertyProfile } from '../api'
import { AmenityPicker } from '../components/AmenityPicker'
import { I18nTextInput } from '../components/I18nTextInput'
import { PhotoGallery } from '../components/PhotoGallery'
import { SaveBar } from '../components/SaveBar'
import { flattenFieldErrors } from '../lib/fieldErrors'

const LANGUAGE_OPTIONS = ['es', 'en', 'fr', 'pt', 'de', 'it']
const BRAND_SWATCHES = ['#B4583B', '#4E6C88', '#5F7F66', '#B98A2E', '#2F6F73', '#6B5B95', '#1F1C19']
const SECTIONS = ['general', 'location', 'legal', 'schedule', 'rules', 'brand', 'photos'] as const
const NO_STARS = 'none'

interface ProfileDraft {
  name: string
  description: I18nText
  star_rating: number | null
  amenities: string[]
  address: string
  city: string
  department: string
  latitude: string
  longitude: string
  phone: string
  email: string
  website: string
  legal_name: string
  nit: string
  rnt_number: string
  check_in_time: string
  check_out_time: string
  default_language: 'es' | 'en'
  languages: string[]
  house_rules: I18nText
  policies: PropertyPolicies
  primary_color: string
}

function draftOf(profile: PropertyProfile): ProfileDraft {
  return {
    name: profile.name,
    description: { ...profile.description },
    star_rating: profile.star_rating,
    amenities: [...profile.amenities],
    address: profile.address,
    city: profile.city,
    department: profile.department,
    latitude: profile.latitude ?? '',
    longitude: profile.longitude ?? '',
    phone: profile.phone,
    email: profile.email,
    website: profile.website,
    legal_name: profile.legal_name,
    nit: profile.nit,
    rnt_number: profile.rnt_number,
    check_in_time: profile.check_in_time,
    check_out_time: profile.check_out_time,
    default_language: profile.default_language,
    languages: [...profile.languages],
    house_rules: { ...profile.house_rules },
    policies: { ...profile.policies },
    primary_color: profile.branding.primary_color ?? '',
  }
}

/** Only what changed, in the shape the API takes (`branding.primary_color`, nulls for empty coordinates). */
function changes(draft: ProfileDraft, baseline: ProfileDraft): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  for (const key of Object.keys(draft) as (keyof ProfileDraft)[]) {
    if (JSON.stringify(draft[key]) === JSON.stringify(baseline[key])) continue
    if (key === 'primary_color') body.branding = { primary_color: draft.primary_color }
    else if (key === 'latitude' || key === 'longitude') body[key] = draft[key] === '' ? null : draft[key]
    else body[key] = draft[key]
  }
  return body
}

/** The hotel's identity: what guests, the marketplace, invoices and the chatbot read about it. */
export default function PropertyPage() {
  const { t } = useTranslation('inventory')
  const profile = usePropertyProfile()
  const membership = useActiveMembership()
  if (profile.isError) {
    return (
      <>
        <PageHeader title={t('nav.property')} />
        <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />
      </>
    )
  }
  if (!profile.data || !membership) {
    return (
      <>
        <PageHeader title={t('nav.property')} description={t('nav.propertyHint')} />
        <LoadingState variant="rows" rows={8} />
      </>
    )
  }
  return <PropertyForm key={profile.data.id} profile={profile.data} />
}

function PropertyForm({ profile }: { profile: PropertyProfile }) {
  const { t, i18n } = useTranslation('inventory')
  const lang = normalizeLang(i18n.language)
  const canEdit = useCan('inventory.manage')
  const invalidate = useInvalidateInventory()
  const amenities = useAmenities()
  const [current, setCurrent] = useState(profile)
  const [baseline, setBaseline] = useState(() => draftOf(profile))
  const [draft, setDraft] = useState(baseline)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const body = changes(draft, baseline)
  const dirty = Object.keys(body).length > 0
  const languageNames = new Intl.DisplayNames([lang], { type: 'language' })

  function patch(next: Partial<ProfileDraft>) {
    setDraft((value) => ({ ...value, ...next }))
    setServerErrors((errors) => {
      const copy = { ...errors }
      for (const key of Object.keys(next)) delete copy[key === 'primary_color' ? 'branding' : key]
      return copy
    })
  }

  const errors: Record<string, string> = {}
  if (!draft.name.trim()) errors.name = t('common:validation.required')
  const errorOf = (field: string) => serverErrors[field] ?? errors[field]

  const save = useMutation({
    mutationFn: () => api.patch<PropertyProfile>('/inventory/property/', body),
    onSuccess: (saved) => {
      toast.success(t('property.saved'))
      setCurrent(saved)
      const next = draftOf(saved)
      setBaseline(next)
      setDraft(next)
      setServerErrors({})
      void invalidate()
    },
    onError: (error) => {
      if (isApiError(error) && error.fields) {
        // nested errors (`branding.primary_color`, `policies.min_checkin_age`, `description.es`) go under
        // the field that shows them
        const byField: Record<string, string> = {}
        for (const [key, message] of Object.entries(flattenFieldErrors(error.fields))) {
          const field = key.split('.')[0] ?? key
          byField[field] = byField[field] ? `${byField[field]} ${message}` : message
        }
        setServerErrors(byField)
      }
      toast.error(errorMessage(error, t))
    },
  })

  const logo = useMutation({
    mutationFn: (file: File | null) => {
      if (!file) return api.delete<PropertyProfile>('/inventory/property/logo/')
      const formData = new FormData()
      formData.append('image', file)
      return api.post<PropertyProfile>('/inventory/property/logo/', undefined, { formData })
    },
    onSuccess: (saved, file) => {
      toast.success(file ? t('property.logoSaved') : t('property.logoRemoved'))
      setCurrent(saved)
      void invalidate()
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  return (
    <>
      <PageHeader
        title={t('nav.property')}
        description={t('nav.propertyHint')}
        actions={
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Badge tone="outline">{t(`common:propertyTypes.${current.property_type}`, { defaultValue: current.property_type })}</Badge>
            <span className="num">{t('property.businessDate', { date: formatDate(current.business_date, 'd MMM yyyy', lang) })}</span>
          </span>
        }
      />
      <nav aria-label={t('property.sections')} className="-mx-4 mb-6 flex gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0">
        {SECTIONS.map((section) => (
          <a key={section} href={`#property-${section}`}
             className="shrink-0 rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold text-muted hover:border-border-strong hover:text-fg">
            {t(`property.section.${section}`)}
          </a>
        ))}
      </nav>

      <fieldset disabled={!canEdit} className="grid gap-8">
        <Section id="general" title={t('property.section.general')}>
          <Field label={t('property.name')} error={errorOf('name')}>
            {(props) => <Input {...props} name="name" maxLength={200} value={draft.name} onChange={(event) => patch({ name: event.target.value })} />}
          </Field>
          <Group label={t('property.description')} hint={t('property.descriptionHint')} error={errorOf('description')}>
            <I18nTextInput label={t('property.description')} name="description" multiline value={draft.description}
                           invalid={Boolean(errorOf('description'))} onChange={(description) => patch({ description })} />
          </Group>
          <Field label={t('property.stars')} error={errorOf('star_rating')}>
            {(props) => (
              <Select name="star_rating" value={draft.star_rating ? String(draft.star_rating) : NO_STARS}
                      onValueChange={(value) => patch({ star_rating: value === NO_STARS ? null : Number(value) })}>
                <SelectTrigger id={props.id} aria-invalid={props['aria-invalid']} className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_STARS}>{t('property.noStars')}</SelectItem>
                  {[1, 2, 3, 4, 5].map((stars) => (
                    <SelectItem key={stars} value={String(stars)}>
                      {'★'.repeat(stars)} · {t('property.starsN', { count: stars })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
          <Group label={t('property.amenities')} hint={t('property.amenitiesHint')} error={errorOf('amenities')}>
            {amenities.data ? (
              <AmenityPicker mode="select" amenities={amenities.data} value={draft.amenities} onChange={(value) => patch({ amenities: value })} />
            ) : (
              <LoadingState variant="rows" rows={2} />
            )}
          </Group>
        </Section>

        <Section id="location" title={t('property.section.location')}>
          <Field label={t('property.address')} error={errorOf('address')}>
            {(props) => <Input {...props} name="address" maxLength={255} value={draft.address} onChange={(event) => patch({ address: event.target.value })} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('property.city')} error={errorOf('city')} stacked>
              {(props) => <Input {...props} name="city" maxLength={100} value={draft.city} onChange={(event) => patch({ city: event.target.value })} />}
            </Field>
            <Field label={t('property.department')} error={errorOf('department')} stacked>
              {(props) => <Input {...props} name="department" maxLength={100} value={draft.department} onChange={(event) => patch({ department: event.target.value })} />}
            </Field>
            <Field label={t('property.latitude')} error={errorOf('latitude')} stacked>
              {(props) => <Input {...props} name="latitude" inputMode="decimal" value={draft.latitude} onChange={(event) => patch({ latitude: event.target.value })} />}
            </Field>
            <Field label={t('property.longitude')} error={errorOf('longitude')} stacked>
              {(props) => <Input {...props} name="longitude" inputMode="decimal" value={draft.longitude} onChange={(event) => patch({ longitude: event.target.value })} />}
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t('property.phone')} error={errorOf('phone')} stacked>
              {(props) => <Input {...props} name="phone" type="tel" value={draft.phone} onChange={(event) => patch({ phone: event.target.value })} />}
            </Field>
            <Field label={t('property.email')} error={errorOf('email')} stacked>
              {(props) => <Input {...props} name="email" type="email" value={draft.email} onChange={(event) => patch({ email: event.target.value })} />}
            </Field>
            <Field label={t('property.website')} error={errorOf('website')} stacked>
              {(props) => <Input {...props} name="website" type="url" placeholder="https://" value={draft.website} onChange={(event) => patch({ website: event.target.value })} />}
            </Field>
          </div>
        </Section>

        <Section id="legal" title={t('property.section.legal')} description={t('property.legalHint')}>
          <Field label={t('property.legalName')} error={errorOf('legal_name')}>
            {(props) => <Input {...props} name="legal_name" maxLength={200} value={draft.legal_name} onChange={(event) => patch({ legal_name: event.target.value })} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('property.nit')} hint={t('property.nitHint')} error={errorOf('nit')} stacked>
              {(props) => <Input {...props} name="nit" className="num" maxLength={30} value={draft.nit} onChange={(event) => patch({ nit: event.target.value })} />}
            </Field>
            <Field label={t('property.rnt')} hint={t('property.rntHint')} error={errorOf('rnt_number')} stacked>
              {(props) => <Input {...props} name="rnt_number" className="num" maxLength={30} value={draft.rnt_number} onChange={(event) => patch({ rnt_number: event.target.value })} />}
            </Field>
          </div>
        </Section>

        <Section id="schedule" title={t('property.section.schedule')}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t('property.checkIn')} error={errorOf('check_in_time')} stacked>
              {(props) => <Input {...props} name="check_in_time" type="time" value={draft.check_in_time} onChange={(event) => patch({ check_in_time: event.target.value })} />}
            </Field>
            <Field label={t('property.checkOut')} error={errorOf('check_out_time')} stacked>
              {(props) => <Input {...props} name="check_out_time" type="time" value={draft.check_out_time} onChange={(event) => patch({ check_out_time: event.target.value })} />}
            </Field>
            <Field label={t('property.defaultLanguage')} hint={t('property.defaultLanguageHint')} error={errorOf('default_language')} stacked>
              {(props) => (
                <Select name="default_language" value={draft.default_language} onValueChange={(value) => patch({ default_language: value as 'es' | 'en' })}>
                  <SelectTrigger id={props.id}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="es">{languageNames.of('es')}</SelectItem>
                    <SelectItem value="en">{languageNames.of('en')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </Field>
          </div>
          <Group label={t('property.languages')} hint={t('property.languagesHint')} error={errorOf('languages')}>
            <div className="flex flex-wrap gap-2">
              {LANGUAGE_OPTIONS.map((code) => {
                const on = draft.languages.includes(code)
                return (
                  <button
                    key={code}
                    type="button"
                    aria-pressed={on}
                    onClick={() => patch({ languages: on ? draft.languages.filter((item) => item !== code) : [...draft.languages, code] })}
                    className={cn(
                      'h-8 rounded-full border px-3 text-[13px] font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                      on ? 'border-accent bg-accent-soft text-accent-ink' : 'border-border bg-surface text-muted hover:text-fg',
                    )}
                  >
                    {languageNames.of(code)}
                  </button>
                )
              })}
            </div>
          </Group>
        </Section>

        <Section id="rules" title={t('property.section.rules')}>
          <Group label={t('property.houseRules')} hint={t('property.houseRulesHint')} error={errorOf('house_rules')}>
            <I18nTextInput label={t('property.houseRules')} name="house_rules" multiline value={draft.house_rules}
                           invalid={Boolean(errorOf('house_rules'))} onChange={(house_rules) => patch({ house_rules })} />
          </Group>
          <div className="grid gap-3 sm:grid-cols-2">
            {(['pets_allowed', 'children_allowed', 'smoking_allowed', 'events_allowed'] as const).map((policy) => (
              <label key={policy} className="flex items-center gap-3">
                <Switch name={`policies.${policy}`} checked={draft.policies[policy]}
                        onCheckedChange={(checked) => patch({ policies: { ...draft.policies, [policy]: checked } })} />
                <span className="text-[13px] font-semibold">{t(`property.policies.${policy}`)}</span>
              </label>
            ))}
          </div>
          <Field label={t('property.policies.min_checkin_age')} error={errorOf('policies')}>
            {(props) => (
              <Input {...props} name="policies.min_checkin_age" type="number" min={0} max={99} className="w-28"
                     value={draft.policies.min_checkin_age ?? ''}
                     onChange={(event) => patch({ policies: { ...draft.policies, min_checkin_age: Number.isFinite(event.target.valueAsNumber) ? event.target.valueAsNumber : null } })} />
            )}
          </Field>
        </Section>

        <Section id="brand" title={t('property.section.brand')} description={t('property.brandHint')}>
          <Group label={t('property.primaryColor')}>
            <div className="flex flex-wrap items-center gap-2">
              {BRAND_SWATCHES.map((color) => (
                <button key={color} type="button" aria-label={color} aria-pressed={draft.primary_color.toLowerCase() === color.toLowerCase()}
                        onClick={() => patch({ primary_color: color })}
                        className={cn('size-8 rounded-md ring-offset-2 ring-offset-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                          draft.primary_color.toLowerCase() === color.toLowerCase() && 'ring-2 ring-fg')}
                        style={{ backgroundColor: color }} />
              ))}
              <Input name="primary_color" aria-label={t('property.primaryColorHex')} className="w-28 num" maxLength={7} value={draft.primary_color}
                     aria-invalid={Boolean(errorOf('branding'))} onChange={(event) => patch({ primary_color: event.target.value })} />
              <span className="inline-flex h-8 items-center rounded-md px-3 text-[13px] font-semibold text-white shadow-xs"
                    style={{ backgroundColor: /^#[0-9a-f]{6}$/i.test(draft.primary_color) ? draft.primary_color : undefined }}>
                {t('property.bookNow')}
              </span>
            </div>
            {errorOf('branding') && <p className="text-xs font-medium text-danger-ink">{errorOf('branding')}</p>}
          </Group>
          <Group label={t('property.logo')} hint={t('property.logoHint')}>
            <div className="flex flex-wrap items-center gap-4">
              <span className="grid h-16 w-32 place-items-center overflow-hidden rounded-lg border border-border bg-surface-2">
                {current.branding.logo ? (
                  <img src={current.branding.logo} alt={t('property.logoAlt', { name: current.name })} className="max-h-14 max-w-28 object-contain" />
                ) : (
                  <span className="text-xs text-subtle">{t('property.noLogo')}</span>
                )}
              </span>
              {canEdit && (
                <>
                  <Button asChild variant="secondary" size="sm">
                    <label className="cursor-pointer">
                      <ImageUp aria-hidden />
                      {current.branding.logo ? t('property.replaceLogo') : t('property.uploadLogo')}
                      <input type="file" name="logo" accept="image/jpeg,image/png,image/webp" className="sr-only"
                             onChange={(event) => {
                               const file = event.target.files?.[0]
                               if (file) logo.mutate(file)
                               event.target.value = ''
                             }} />
                    </label>
                  </Button>
                  {current.branding.logo && (
                    <Button variant="ghost" size="sm" onClick={() => logo.mutate(null)} loading={logo.isPending}>
                      <Trash2 aria-hidden />
                      {t('property.removeLogo')}
                    </Button>
                  )}
                </>
              )}
            </div>
          </Group>
        </Section>
      </fieldset>

      <Section id="photos" title={t('property.section.photos')} description={t('property.photosHint')}>
        <PhotoGallery roomTypeId={null} canEdit={canEdit} label={t('photos.propertyPhotos')} />
      </Section>

      <SaveBar
        visible={canEdit && dirty}
        saving={save.isPending}
        disabled={Object.keys(errors).length > 0}
        problem={Object.keys(errors).length > 0 ? t('roomEditor.fixErrors') : undefined}
        onSave={() => save.mutate()}
        onDiscard={() => {
          setDraft(baseline)
          setServerErrors({})
        }}
      />
    </>
  )
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={`property-${id}`} aria-labelledby={`property-${id}-title`} className="grid scroll-mt-24 gap-3">
      <div>
        <h2 id={`property-${id}-title`} className="text-[15px] text-fg">
          {title}
        </h2>
        {description && <p className="mt-0.5 max-w-2xl text-[13px] text-muted">{description}</p>}
      </div>
      <div className="grid gap-5 rounded-lg border border-border bg-surface p-4 shadow-xs sm:p-5">{children}</div>
    </section>
  )
}

interface ControlProps {
  id: string
  'aria-invalid': boolean
  'aria-describedby'?: string
}

function Field({ label, hint, error, stacked, children }: {
  label: string
  hint?: string
  error?: string
  stacked?: boolean
  children: (props: ControlProps) => ReactNode
}) {
  const id = useId()
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(' ') || undefined
  return (
    <div className={cn('grid gap-1.5', !stacked && 'sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)] sm:items-start sm:gap-4')}>
      <label htmlFor={id} className={cn('text-[13px] font-semibold text-fg', !stacked && 'sm:pt-2')}>
        {label}
      </label>
      <div className="grid gap-1">
        {children({ id, 'aria-invalid': Boolean(error), 'aria-describedby': describedBy })}
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-muted">
            {hint}
          </p>
        )}
        {error && (
          <p id={`${id}-error`} className="text-xs font-medium text-danger-ink" aria-live="polite">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}

function Group({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  const id = useId()
  return (
    <div
      role="group"
      aria-labelledby={id}
      aria-describedby={error ? `${id}-error` : undefined}
      className="grid gap-1.5 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)] sm:items-start sm:gap-4"
    >
      <span id={id} className="text-[13px] font-semibold text-fg sm:pt-2">
        {label}
      </span>
      <div className="grid gap-1.5">
        {children}
        {hint && <p className="text-xs text-muted">{hint}</p>}
        {error && (
          <p id={`${id}-error`} className="text-xs font-medium text-danger-ink" aria-live="polite">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
