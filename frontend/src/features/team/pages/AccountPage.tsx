import { zodResolver } from '@hookform/resolvers/zod'
import { MailWarning, ShieldCheck } from 'lucide-react'
import { useId, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { isApiError } from '@/lib/api'
import { useMe, type Me } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { emailVerifiedAt, isEmailUnverified, useChangePassword } from '../account-api'
import { DevMailboxHint } from '../components/AccessLayout'
import { PasswordInput } from '../components/PasswordInput'
import { PasswordRules } from '../components/PasswordRules'
import { ResendVerificationButton } from '../components/ResendVerificationButton'
import { fieldMessages, isThrottled, MIN_PASSWORD } from '../password'

/** `/app/settings/account` "My account and security": the email and its verification, and the password. */
export default function AccountPage() {
  const { t } = useTranslation('team')
  const { data: me } = useMe()
  if (!me) return null // RequireAuth renders this page only with a session
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title={t('account.title')} description={t('account.description')} />
      <div className="grid grid-cols-1 gap-6">
        <EmailCard me={me} />
        <PasswordCard email={me.email} />
      </div>
    </div>
  )
}

function EmailCard({ me }: { me: Me }) {
  const { t, i18n } = useTranslation('team')
  const unverified = isEmailUnverified(me)
  const verifiedAt = emailVerifiedAt(me)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('account.email.title')}</CardTitle>
        <CardDescription>{t('account.email.description')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="min-w-0 font-semibold break-all text-fg">{me.email}</span>
          {unverified ? (
            <Badge tone="warning">
              <MailWarning aria-hidden />
              {t('account.email.unverified')}
            </Badge>
          ) : (
            <Badge tone="success">
              <ShieldCheck aria-hidden />
              {t('account.email.verified')}
            </Badge>
          )}
        </div>
        {unverified ? (
          <div className="grid gap-3 rounded-md border border-warning/35 bg-warning-soft p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
            <p className="text-sm text-warning-ink">{t('account.email.pending')}</p>
            <ResendVerificationButton size="sm" className="justify-self-start" />
          </div>
        ) : (
          verifiedAt && (
            <p className="text-sm text-muted">
              {t('account.email.verifiedOn', { date: formatDate(verifiedAt, undefined, normalizeLang(i18n.language)) })}
            </p>
          )
        )}
        {unverified && <DevMailboxHint className="" />}
      </CardContent>
    </Card>
  )
}

const passwordSchema = z
  .object({
    current: z.string().min(1, 'team:account.password.currentRequired'),
    password: z
      .string()
      .min(MIN_PASSWORD, 'team:password.tooShort')
      .refine((value) => !/^\d+$/.test(value), 'team:password.onlyNumbers'),
    confirm: z.string().min(1, 'team:password.confirmRequired'),
  })
  .refine((values) => values.password === values.confirm, { path: ['confirm'], message: 'team:password.mismatch' })
type PasswordValues = z.infer<typeof passwordSchema>

const EMPTY: PasswordValues = { current: '', password: '', confirm: '' }

function PasswordCard({ email }: { email: string }) {
  const { t } = useTranslation('team')
  const change = useChangePassword()
  const rulesId = useId()
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<PasswordValues>({ resolver: zodResolver(passwordSchema), defaultValues: EMPTY })
  const [password = '', confirm = ''] = useWatch({ control: form.control, name: ['password', 'confirm'] })

  async function onSubmit(values: PasswordValues) {
    setFailure(null)
    try {
      await change.mutateAsync({ current_password: values.current, new_password: values.password })
      form.reset(EMPTY)
      toast.success(t('account.password.changed'))
    } catch (error) {
      const code = isApiError(error) ? error.code : ''
      const serverMessage = fieldMessages(error, 'new_password')
      if (code === 'wrong_password') {
        form.setError('current', { message: 'team:account.password.wrongCurrent' }, { shouldFocus: true })
      } else if (code === 'same_password') {
        form.setError('password', { message: 'team:account.password.samePassword' }, { shouldFocus: true })
      } else if (serverMessage) {
        form.setError('password', { message: serverMessage }, { shouldFocus: true })
      } else {
        setFailure(isThrottled(error) ? t('errors.throttled') : errorMessage(error, t))
      }
    }
  }

  return (
    <Card>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <CardHeader>
          <CardTitle>{t('account.password.title')}</CardTitle>
          <CardDescription>{t('account.password.description')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {/* Lets password managers file the new password under this account. */}
          <input type="email" name="username" autoComplete="username" value={email} readOnly hidden />
          <FormField
            control={form.control}
            name="current"
            label={t('account.password.current')}
            className="sm:max-w-sm"
            render={({ field, ...a11y }) => <PasswordInput autoComplete="current-password" {...field} {...a11y} />}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="password"
              label={t('account.password.new')}
              render={({ field, ...a11y }) => (
                <PasswordInput
                  autoComplete="new-password"
                  {...field}
                  {...a11y}
                  aria-describedby={[a11y['aria-describedby'], rulesId].filter(Boolean).join(' ')}
                />
              )}
            />
            <FormField
              control={form.control}
              name="confirm"
              label={t('account.password.confirm')}
              render={({ field, ...a11y }) => <PasswordInput autoComplete="new-password" {...field} {...a11y} />}
            />
          </div>
          <PasswordRules id={rulesId} password={password} confirm={confirm} />
          {failure && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {failure}
            </p>
          )}
        </CardContent>
        <CardFooter className="flex-wrap justify-between gap-x-4 gap-y-3">
          <p className="max-w-md text-[13px] text-muted">
            {t('account.password.sessionsNote')}{' '}
            <Link
              to={`/forgot-password?email=${encodeURIComponent(email)}`}
              className="font-semibold text-accent-ink underline-offset-4 hover:underline"
            >
              {t('account.password.forgot')}
            </Link>
          </p>
          <Button type="submit" variant="primary" loading={change.isPending}>
            {t('account.password.submit')}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
