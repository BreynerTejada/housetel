import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, Check, Eye, EyeOff, Info } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Controller, useForm, useWatch, type FieldPath } from 'react-hook-form'
import { Trans, useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { isApiError } from '@/lib/api'
import { useMe } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/utils'
import { usePublicPlans, useSignup, type PublicPlan } from '../api'
import { KeyBoardPreview } from '../components/KeyBoardPreview'
import { pickText } from '../helpers'

const PROPERTY_TYPES = ['hotel', 'boutique', 'hostel', 'aparthotel', 'glamping'] as const

// The 32 departments of Colombia plus the capital district (proper names, the same in every language).
const DEPARTMENTS = [
  'Amazonas', 'Antioquia', 'Arauca', 'Atlántico', 'Bogotá D.C.', 'Bolívar', 'Boyacá', 'Caldas', 'Caquetá',
  'Casanare', 'Cauca', 'Cesar', 'Chocó', 'Córdoba', 'Cundinamarca', 'Guainía', 'Guaviare', 'Huila', 'La Guajira',
  'Magdalena', 'Meta', 'Nariño', 'Norte de Santander', 'Putumayo', 'Quindío', 'Risaralda',
  'San Andrés y Providencia', 'Santander', 'Sucre', 'Tolima', 'Valle del Cauca', 'Vaupés', 'Vichada',
]

const MIN_PASSWORD = 8

const schema = z.object({
  hotel_name: z.string().trim().min(3, 'saas:signup.errors.hotelName'),
  property_type: z.enum(PROPERTY_TYPES),
  city: z.string().trim().min(2, 'validation.required'),
  department: z.string(),
  rooms_estimate: z.number({ error: 'validation.number' }).int('validation.number').min(1, 'saas:signup.errors.rooms').max(5000, 'saas:signup.errors.rooms'),
  owner_name: z.string().trim().min(2, 'validation.required'),
  email: z.string().trim().min(1, 'validation.required').pipe(z.email('validation.email')),
  phone: z.string().trim(),
  password: z.string().min(MIN_PASSWORD, 'saas:signup.errors.password'),
  accept_terms: z.boolean().refine((value) => value, 'saas:signup.errors.terms'),
})

type SignupValues = z.infer<typeof schema>

const STEP_ONE: FieldPath<SignupValues>[] = ['hotel_name', 'property_type', 'city', 'department', 'rooms_estimate']
const STEP_TWO: FieldPath<SignupValues>[] = ['owner_name', 'email', 'phone', 'password', 'accept_terms']

/** Smallest active plan that fits the rooms / beds (the same rule the backend applies at signup). */
function suggestedPlan(plans: PublicPlan[] | undefined, units: number): PublicPlan | null {
  if (!plans?.length) return null
  const sorted = [...plans].sort((a, b) => Number(a.price_monthly) - Number(b.price_monthly))
  return sorted.find((plan) => plan.max_units === null || units <= plan.max_units) ?? sorted.at(-1) ?? null
}

/** `/signup` (public): a hotel creates its Housetel account in two steps and lands on the getting-started
 * checklist with a 14-day trial. */
export default function SignupPage() {
  const { t, i18n } = useTranslation('saas')
  const navigate = useNavigate()
  const { data: me } = useMe()
  const plans = usePublicPlans()
  const signup = useSignup()
  const [step, setStep] = useState<1 | 2>(1)
  const [showPassword, setShowPassword] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const form = useForm<SignupValues>({
    resolver: zodResolver(schema),
    mode: 'onTouched',
    defaultValues: {
      hotel_name: '',
      property_type: 'hotel',
      city: '',
      department: '',
      rooms_estimate: 12,
      owner_name: '',
      email: '',
      phone: '',
      password: '',
      accept_terms: false,
    },
  })
  const [hotelName, city, propertyType, rooms] = useWatch({
    control: form.control,
    name: ['hotel_name', 'city', 'property_type', 'rooms_estimate'],
  })
  const units = Number.isFinite(rooms) ? Math.max(0, rooms) : 0
  const plan = useMemo(() => suggestedPlan(plans.data, units || 1), [plans.data, units])

  async function next() {
    if (await form.trigger(STEP_ONE)) {
      setStep(2)
      window.requestAnimationFrame(() => form.setFocus('owner_name'))
    }
  }

  async function onSubmit(values: SignupValues) {
    setFailure(null)
    try {
      const result = await signup.mutateAsync({
        ...values,
        hotel_name: values.hotel_name.trim(),
        language: i18n.language.startsWith('en') ? 'en' : 'es',
      })
      toast.success(t('signup.done', { name: values.hotel_name.trim() }))
      navigate(result.redirect || '/app/getting-started', { replace: true })
    } catch (error) {
      if (isApiError(error) && error.fields) {
        let firstStep: 1 | 2 | null = null
        for (const [field, messages] of Object.entries(error.fields)) {
          const name = field as FieldPath<SignupValues>
          if (![...STEP_ONE, ...STEP_TWO].includes(name)) continue
          form.setError(name, { message: messages[0] })
          const fieldStep = STEP_ONE.includes(name) ? 1 : 2
          firstStep = firstStep === 1 ? 1 : fieldStep
        }
        if (firstStep) {
          setStep(firstStep)
          return
        }
      }
      if (isApiError(error) && (error.status === 429 || error.code === 'throttled')) setFailure(t('signup.errors.throttled'))
      else setFailure(errorMessage(error, t))
    }
  }

  const typeLabel = t(`common:propertyTypes.${propertyType}`)

  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-6xl flex-1 gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-12">
      {/* Why + the live key board */}
      <section className="flex flex-col gap-6 rounded-2xl border border-border bg-surface-2 p-5 sm:p-8 lg:p-10">
        <div>
          <p className="eyebrow !text-accent-ink">{t('signup.eyebrow')}</p>
          <p className="mt-4 max-w-md text-[30px] leading-[1.05] font-extrabold tracking-[-0.04em] text-balance text-fg sm:text-[40px]">
            {t('signup.headline')}
          </p>
          <p className="mt-3 max-w-md text-muted">{t('signup.subhead')}</p>
        </div>
        <KeyBoardPreview
          hotelName={hotelName}
          city={city}
          typeLabel={typeLabel}
          units={units}
          plan={plan}
          compact={false}
        />
        <ul className="grid grid-cols-1 gap-2.5 text-sm text-fg">
          {(['trial', 'included', 'onboarding'] as const).map((key) => (
            <li key={key} className="flex items-start gap-2.5">
              <span aria-hidden className="mt-0.5 grid grid-cols-1 size-5 shrink-0 place-items-center rounded-full bg-success-soft text-success-ink">
                <Check className="size-3.5" strokeWidth={3} />
              </span>
              {t(`signup.benefits.${key}`)}
            </li>
          ))}
        </ul>
      </section>

      {/* Form */}
      <section className="flex flex-col justify-center">
        <div className="mx-auto w-full max-w-md">
          <p className="num text-sm font-semibold text-muted" aria-live="polite">
            {t('signup.step', { step, total: 2 })} · {step === 1 ? t('signup.stepHotel') : t('signup.stepAccount')}
          </p>
          <div aria-hidden className="mt-2 grid grid-cols-2 gap-1.5">
            <span className="h-1 rounded-full bg-accent" />
            <span className={cn('h-1 rounded-full transition-colors', step === 2 ? 'bg-accent' : 'bg-border')} />
          </div>
          <h1 className="mt-5 text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-fg">
            {step === 1 ? t('signup.titleHotel') : t('signup.titleAccount')}
          </h1>
          <p className="mt-1.5 text-muted">{step === 1 ? t('signup.subtitleHotel') : t('signup.subtitleAccount')}</p>

          {me && (
            <p className="mt-5 flex items-start gap-2 rounded-md bg-info-soft px-3 py-2 text-sm text-info-ink">
              <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span>
                {t('signup.signedIn', { email: me.email })}{' '}
                <Link to="/app" className="font-semibold underline underline-offset-4">
                  {t('signup.goToApp')}
                </Link>
              </span>
            </p>
          )}

          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-7 grid grid-cols-1 gap-4" noValidate>
            <div className={cn('grid grid-cols-1 gap-4', step !== 1 && 'hidden')}>
              <FormField
                control={form.control}
                name="hotel_name"
                label={t('signup.fields.hotelName')}
                render={({ field, ...a11y }) => (
                  <Input autoComplete="organization" placeholder={t('signup.fields.hotelNamePlaceholder')} className="h-10" {...field} {...a11y} />
                )}
              />
              <FormField
                control={form.control}
                name="property_type"
                label={t('signup.fields.propertyType')}
                render={({ field, id, ...a11y }) => (
                  <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id={id} className="h-10" {...a11y}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PROPERTY_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>
                          {t(`common:propertyTypes.${type}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="city"
                  label={t('signup.fields.city')}
                  render={({ field, ...a11y }) => (
                    <Input autoComplete="address-level2" placeholder={t('signup.fields.cityPlaceholder')} className="h-10" {...field} {...a11y} />
                  )}
                />
                <FormField
                  control={form.control}
                  name="department"
                  label={t('signup.fields.department')}
                  render={({ field, id, ...a11y }) => (
                    <Select name={field.name} value={field.value || undefined} onValueChange={field.onChange}>
                      <SelectTrigger id={id} className="h-10" {...a11y}>
                        <SelectValue placeholder={t('signup.fields.departmentPlaceholder')} />
                      </SelectTrigger>
                      <SelectContent className="max-h-72">
                        {DEPARTMENTS.map((name) => (
                          <SelectItem key={name} value={name}>
                            {name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="rooms_estimate"
                label={t('signup.fields.rooms')}
                description={t('signup.fields.roomsHint')}
                render={({ field, ...a11y }) => (
                  <Input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={5000}
                    className="num h-10 max-w-40"
                    name={field.name}
                    ref={field.ref}
                    onBlur={field.onBlur}
                    value={Number.isFinite(field.value) ? field.value : ''}
                    onChange={(event) => field.onChange(event.target.value === '' ? Number.NaN : event.target.valueAsNumber)}
                    {...a11y}
                  />
                )}
              />
              {plan && (
                <p className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">
                  <Trans
                    t={t}
                    i18nKey="signup.planHint"
                    values={{ plan: pickText(plan.name, i18n.language), price: formatMoney(plan.price_monthly) }}
                    components={{ strong: <strong className="font-semibold text-fg" /> }}
                  />
                </p>
              )}
              <Button type="button" variant="primary" size="lg" className="mt-2 w-full" onClick={() => void next()}>
                {t('signup.next')}
              </Button>
            </div>

            <div className={cn('grid grid-cols-1 gap-4', step !== 2 && 'hidden')}>
              <FormField
                control={form.control}
                name="owner_name"
                label={t('signup.fields.ownerName')}
                render={({ field, ...a11y }) => <Input autoComplete="name" className="h-10" {...field} {...a11y} />}
              />
              <FormField
                control={form.control}
                name="email"
                label={t('signup.fields.email')}
                render={({ field, ...a11y }) => (
                  <Input type="email" inputMode="email" autoComplete="email" placeholder="tu@hotel.co" className="h-10" {...field} {...a11y} />
                )}
              />
              <FormField
                control={form.control}
                name="phone"
                label={t('signup.fields.phone')}
                description={t('signup.fields.phoneHint')}
                render={({ field, ...a11y }) => (
                  <Input type="tel" inputMode="tel" autoComplete="tel" placeholder="300 123 4567" className="h-10" {...field} {...a11y} />
                )}
              />
              <FormField
                control={form.control}
                name="password"
                label={t('signup.fields.password')}
                description={t('signup.fields.passwordHint', { min: MIN_PASSWORD })}
                render={({ field, ...a11y }) => (
                  <div className="relative">
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      className="h-10 pr-10"
                      {...field}
                      {...a11y}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      aria-label={showPassword ? t('signup.hidePassword') : t('signup.showPassword')}
                      aria-pressed={showPassword}
                      className="absolute inset-y-0 right-0 grid grid-cols-1 w-10 place-items-center rounded-r-md text-subtle hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      {showPassword ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
                    </button>
                  </div>
                )}
              />
              <Controller
                control={form.control}
                name="accept_terms"
                render={({ field, fieldState }) => (
                  <div className="grid grid-cols-1 gap-1.5">
                    <div className="flex items-start gap-2.5">
                      <Checkbox
                        id="signup-terms"
                        name={field.name}
                        checked={field.value}
                        onCheckedChange={(value) => field.onChange(value === true)}
                        onBlur={field.onBlur}
                        aria-invalid={Boolean(fieldState.error)}
                        aria-describedby={fieldState.error ? 'signup-terms-error' : undefined}
                        className="mt-0.5"
                      />
                      <label htmlFor="signup-terms" className="text-sm leading-snug text-muted">
                        {t('signup.fields.terms')}
                      </label>
                    </div>
                    {fieldState.error?.message && (
                      <p id="signup-terms-error" className="text-xs font-medium text-danger-ink">
                        {i18n.exists(fieldState.error.message) ? t(fieldState.error.message) : fieldState.error.message}
                      </p>
                    )}
                  </div>
                )}
              />
              {failure && (
                <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
                  {failure}
                </p>
              )}
              <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row">
                <Button type="button" variant="secondary" size="lg" onClick={() => setStep(1)} disabled={signup.isPending}>
                  <ArrowLeft aria-hidden />
                  {t('signup.back')}
                </Button>
                <Button type="submit" variant="primary" size="lg" className="flex-1" loading={signup.isPending}>
                  {signup.isPending ? t('signup.creating') : t('signup.submit')}
                </Button>
              </div>
            </div>
          </form>

          <p className="mt-8 text-sm text-muted">
            {t('signup.haveAccount')}{' '}
            <Link to="/login" className="font-semibold text-fg underline underline-offset-4">
              {t('signup.login')}
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
