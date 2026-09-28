import { useQueryClient } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { homeFor, ME_QUERY_KEY, useMe } from '@/lib/auth'
import { isEmailUnverified, useVerifyEmail } from '../account-api'
import { KeySleeve, Stamp } from '../components/KeyCard'
import { ResendVerificationButton } from '../components/ResendVerificationButton'

const ACCOUNT_PATH = '/app/settings/account'

/**
 * `/verify-email/:verifyToken` (public; the link of the verification email). Confirms the address on load —
 * no session needed, so it works on the phone where the email was opened.
 */
export default function VerifyEmailPage() {
  const { t } = useTranslation('team')
  const { verifyToken = '' } = useParams()
  const verify = useVerifyEmail(verifyToken)
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const verified = verify.isSuccess

  // Signed in on this browser: refresh `Me` so the "Verify your email" reminders disappear.
  useEffect(() => {
    if (verified) void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
  }, [verified, queryClient])

  const placeholder = t('scene.accountPlaceholder')

  if (verify.isPending) {
    return (
      <Shell sleeve={<KeySleeve account={me?.email} placeholder={placeholder} />}>
        <p role="status" className="inline-flex items-center gap-2 text-sm text-muted">
          <LoaderCircle aria-hidden className="size-4 animate-spin text-accent" />
          {t('verify.checking')}
        </p>
      </Shell>
    )
  }

  if (verify.isSuccess) {
    const { email, already_verified: already } = verify.data
    return (
      <Shell sleeve={<KeySleeve account={email} placeholder={placeholder} stamp={<Stamp tone="success">{t('scene.verified')}</Stamp>} />}>
        <h1 className="text-[26px] leading-tight font-extrabold tracking-[-0.03em] text-fg">{t('verify.doneTitle')}</h1>
        <p className="mt-2 break-words text-muted">{already ? t('verify.alreadyText', { email }) : t('verify.doneText', { email })}</p>
        <Button asChild variant="primary" className="mt-6">
          <Link to={me ? homeFor(me) : '/login'}>{me ? t('verify.goToApp') : t('verify.login')}</Link>
        </Button>
      </Shell>
    )
  }

  const code = isApiError(verify.error) ? verify.error.code : ''
  if (code !== 'token_expired' && code !== 'invalid_token') {
    return <ErrorState error={verify.error} onRetry={() => void verify.refetch()} className="flex-1" />
  }
  const expired = code === 'token_expired'
  return (
    <Shell
      sleeve={
        <KeySleeve
          account={me?.email}
          placeholder={placeholder}
          stamp={<Stamp tone={expired ? 'warning' : 'danger'}>{expired ? t('scene.expired') : t('scene.invalid')}</Stamp>}
        />
      }
    >
      <h1 className="text-[26px] leading-tight font-extrabold tracking-[-0.03em] text-fg">
        {expired ? t('verify.expiredTitle') : t('verify.invalidTitle')}
      </h1>
      <p className="mt-2 text-muted">{expired ? t('verify.expiredText') : t('verify.invalidText')}</p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
        {!me ? (
          <Button asChild variant="primary">
            <Link to={`/login?next=${encodeURIComponent(ACCOUNT_PATH)}`}>{t('verify.loginToResend')}</Link>
          </Button>
        ) : isEmailUnverified(me) ? (
          <ResendVerificationButton variant="primary" />
        ) : (
          <Button asChild variant="primary">
            <Link to={homeFor(me)}>{t('verify.goToApp')}</Link>
          </Button>
        )}
      </div>
    </Shell>
  )
}

function Shell({ sleeve, children }: { sleeve: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-4 py-12 text-center sm:py-16">
      <div aria-hidden className="w-full max-w-[17.5rem] pb-4">
        {sleeve}
      </div>
      <div className="mt-8 w-full">{children}</div>
    </div>
  )
}
