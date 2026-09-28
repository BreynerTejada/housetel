import { zodResolver } from '@hookform/resolvers/zod'
import { useId, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { homeFor } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useResetLink, useResetPassword } from '../account-api'
import { AccessLayout, BackToLogin } from '../components/AccessLayout'
import { KeyCard, RecodeScene } from '../components/KeyCard'
import { PasswordInput } from '../components/PasswordInput'
import { PasswordRules } from '../components/PasswordRules'
import { fieldMessages, isThrottled, MIN_PASSWORD } from '../password'

const schema = z
  .object({
    password: z
      .string()
      .min(MIN_PASSWORD, 'team:password.tooShort')
      .refine((value) => !/^\d+$/.test(value), 'team:password.onlyNumbers'),
    confirm: z.string().min(1, 'team:password.confirmRequired'),
  })
  .refine((values) => values.password === values.confirm, { path: ['confirm'], message: 'team:password.mismatch' })
type ResetValues = z.infer<typeof schema>

const describedBy = (...ids: (string | undefined)[]) => ids.filter(Boolean).join(' ') || undefined

/**
 * `/reset-password/:uid/:resetToken` (public; the link of the reset email). Checks the link first, then
 * asks for the new password; saving signs the user in here and out everywhere else.
 */
export default function ResetPasswordPage() {
  const { t } = useTranslation('team')
  const { uid = '', resetToken = '' } = useParams()
  const link = useResetLink(uid, resetToken)

  if (link.isPending) return <LoadingState className="flex-1" label={t('reset.checking')} />
  if (link.isError) {
    if (isApiError(link.error) && link.error.code === 'invalid_token') return <LinkNotValid />
    return <ErrorState error={link.error} onRetry={() => void link.refetch()} className="flex-1" />
  }
  return <ResetForm uid={uid} token={resetToken} account={link.data.email} onStale={() => void link.refetch()} />
}

function ResetForm({ uid, token, account, onStale }: { uid: string; token: string; account: string; onStale: () => void }) {
  const { t } = useTranslation('team')
  const navigate = useNavigate()
  const reset = useResetPassword()
  const rulesId = useId()
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<ResetValues>({ resolver: zodResolver(schema), defaultValues: { password: '', confirm: '' } })
  const [password = '', confirm = ''] = useWatch({ control: form.control, name: ['password', 'confirm'] })

  async function onSubmit(values: ResetValues) {
    setFailure(null)
    try {
      const me = await reset.mutateAsync({ uid, token, new_password: values.password })
      toast.success(t('reset.done'))
      navigate(homeFor(me), { replace: true })
    } catch (error) {
      const serverMessage = fieldMessages(error, 'new_password')
      if (isApiError(error) && error.code === 'invalid_token') onStale() // the page switches to "link no longer works"
      else if (serverMessage) form.setError('password', { message: serverMessage }, { shouldFocus: true })
      else setFailure(isThrottled(error) ? t('errors.throttled') : errorMessage(error, t))
    }
  }

  return (
    <AccessLayout eyebrow={t('reset.eyebrow')} scene={<RecodeScene account={account} />}>
      <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-balance text-fg">{t('reset.title')}</h1>
      <p className="mt-1.5 break-words text-muted">{t('reset.subtitle', { email: account })}</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-8 grid gap-4" noValidate>
        <FormField
          control={form.control}
          name="password"
          label={t('reset.password')}
          render={({ field, ...a11y }) => (
            <PasswordInput
              autoComplete="new-password"
              autoFocus
              {...field}
              {...a11y}
              aria-describedby={describedBy(a11y['aria-describedby'], rulesId)}
            />
          )}
        />
        <FormField
          control={form.control}
          name="confirm"
          label={t('reset.confirm')}
          render={({ field, ...a11y }) => <PasswordInput autoComplete="new-password" {...field} {...a11y} />}
        />
        <PasswordRules id={rulesId} password={password} confirm={confirm} />
        <p className="text-[13px] text-muted">{t('reset.sessionsNote')}</p>
        {failure && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {failure}
          </p>
        )}
        <Button type="submit" variant="primary" size="lg" className="mt-2 w-full" loading={reset.isPending}>
          {t('reset.submit')}
        </Button>
      </form>
      <BackToLogin />
    </AccessLayout>
  )
}

/** Used, expired or mangled link: say so and offer a new one. */
function LinkNotValid() {
  const { t } = useTranslation('team')
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-4 py-16 text-center">
      <div aria-hidden className="relative aspect-[1.586] w-44 -rotate-3">
        <KeyCard tone="void" />
      </div>
      <h1 className="mt-8 text-[24px] leading-tight font-extrabold tracking-[-0.03em] text-fg">{t('reset.invalidTitle')}</h1>
      <p className="mt-2 text-muted">{t('reset.invalidText')}</p>
      <Button asChild variant="primary" className="mt-6">
        <Link to="/forgot-password">{t('reset.requestNew')}</Link>
      </Button>
      <BackToLogin />
    </div>
  )
}
