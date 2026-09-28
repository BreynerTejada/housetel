import { Send } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button, type ButtonProps } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useResendCooldown, useResendVerification } from '../account-api'
import { isThrottled } from '../password'

function resendError(error: unknown, t: TFunction): string {
  if (isThrottled(error)) return t('verification.throttled')
  if (isApiError(error) && error.code === 'email_unavailable') return t('verification.emailUnavailable')
  return errorMessage(error, t)
}

/**
 * "Resend link" for the signed-in user's verification email (topbar chip, account page, expired link).
 * After a send it waits RESEND_COOLDOWN seconds, shared by every copy of the button in the tab.
 */
export function ResendVerificationButton({
  variant = 'secondary',
  size = 'md',
  className,
  onDone,
}: Pick<ButtonProps, 'variant' | 'size' | 'className'> & { onDone?: () => void }) {
  const { t } = useTranslation('team')
  const resend = useResendVerification()
  const cooldown = useResendCooldown()

  function run() {
    resend.mutate(undefined, {
      onSuccess: (result) => {
        toast.success(result.email_verified ? t('verification.alreadyVerified') : t('verification.sent', { email: result.email }))
        onDone?.()
      },
      onError: (error) => toast.error(resendError(error, t)),
    })
  }

  return (
    <Button variant={variant} size={size} className={className} onClick={run} loading={resend.isPending} disabled={cooldown > 0}>
      {!resend.isPending && <Send aria-hidden />}
      {cooldown > 0 ? t('verification.resendIn', { seconds: cooldown }) : t('verification.resend')}
    </Button>
  )
}
