import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useSearchParams } from 'react-router'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api'
import { homeFor, safeNext, useLogin, useMe } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { RoomRack } from './login/RoomRack'

const schema = z.object({
  email: z.string().trim().min(1, 'validation.required').pipe(z.email('validation.email')),
  password: z.string().min(1, 'validation.required'),
})
type LoginValues = z.infer<typeof schema>

const DEMO_PASSWORD = 'housetel123'
// Seeded demo users (spec §10); only listed in development builds.
const DEMO_ACCOUNTS = [
  { email: 'owner@casaaurora.co', labelKey: 'auth.demoOwner' },
  { email: 'recepcion@casaaurora.co', labelKey: 'auth.demoFrontDesk' },
  { email: 'limpieza@casaaurora.co', labelKey: 'auth.demoHousekeeping' },
  { email: 'admin@housetel.co', labelKey: 'auth.demoAdmin' },
]

export function LoginPage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const { data: me } = useMe()
  const login = useLogin()
  const [showPassword, setShowPassword] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<LoginValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  // Signed in (already, or right after submitting): continue where the user was going.
  if (me) return <Navigate to={safeNext(params.get('next')) ?? homeFor(me)} replace />

  async function onSubmit(values: LoginValues) {
    setFailure(null)
    try {
      await login.mutateAsync(values)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'invalid_credentials') setFailure(t('auth.invalidCredentials'))
      else if (error instanceof ApiError && (error.status === 429 || error.code === 'throttled')) setFailure(t('auth.throttled'))
      else setFailure(errorMessage(error, t))
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-12">
      <section className="hidden flex-col rounded-2xl border border-border bg-surface-2 p-10 lg:flex">
        <p className="eyebrow !text-accent-ink">{t('auth.eyebrow')}</p>
        <p className="mt-5 max-w-md text-[44px] leading-[1.02] font-extrabold tracking-[-0.04em] text-balance text-fg">
          {t('auth.headline')}
        </p>
        <p className="mt-4 max-w-md text-muted">{t('auth.subhead')}</p>
        <div className="mt-auto pt-12">
          <RoomRack />
        </div>
      </section>

      <section className="flex flex-col justify-center">
        <div className="mx-auto w-full max-w-sm">
          <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-fg">{t('auth.title')}</h1>
          <p className="mt-1.5 text-muted">{t('auth.subtitle')}</p>

          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-8 grid gap-4" noValidate>
            <FormField
              control={form.control}
              name="email"
              label={t('auth.email')}
              render={({ field, ...a11y }) => (
                <Input
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  placeholder={t('auth.emailPlaceholder')}
                  className="h-10"
                  {...field}
                  {...a11y}
                />
              )}
            />
            <FormField
              control={form.control}
              name="password"
              label={t('auth.password')}
              render={({ field, ...a11y }) => (
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    className="h-10 pr-10"
                    {...field}
                    {...a11y}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
                    aria-pressed={showPassword}
                    className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-subtle hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                  >
                    {showPassword ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
                  </button>
                </div>
              )}
            />
            {failure && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
                {failure}
              </p>
            )}
            <Button type="submit" variant="primary" size="lg" className="mt-2 w-full" loading={login.isPending}>
              {login.isPending ? t('auth.submitting') : t('auth.submit')}
            </Button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-8 rounded-lg border border-dashed border-border-strong p-4">
              <p className="text-[13px] font-bold text-fg">{t('auth.demoTitle')}</p>
              <p className="num mt-0.5 text-xs text-muted">{t('auth.demoHint', { password: DEMO_PASSWORD })}</p>
              <ul className="mt-3 grid gap-1">
                {DEMO_ACCOUNTS.map((account) => (
                  <li key={account.email}>
                    <button
                      type="button"
                      title={t('auth.demoUse')}
                      onClick={() => {
                        form.setValue('email', account.email, { shouldValidate: true })
                        form.setValue('password', DEMO_PASSWORD, { shouldValidate: true })
                      }}
                      className="flex w-full flex-col rounded-md px-2 py-1.5 text-left transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      <span className="text-[13px] font-semibold text-fg">{t(account.labelKey)}</span>
                      <span className="text-xs text-muted">{account.email}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="mt-8 text-sm text-muted">
            {t('auth.noAccount')}{' '}
            <Link to="/signup" className="font-semibold text-accent-ink underline-offset-4 hover:underline">
              {t('auth.signup')}
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}

export default LoginPage
