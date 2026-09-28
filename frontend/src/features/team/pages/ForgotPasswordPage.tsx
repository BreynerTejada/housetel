import { zodResolver } from '@hookform/resolvers/zod'
import { MailCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/errors'
import { useForgotPassword } from '../account-api'
import { AccessLayout, BackToLogin, DevMailboxHint } from '../components/AccessLayout'
import { KeySleeve, Stamp } from '../components/KeyCard'
import { useCooldown } from '../hooks'
import { isThrottled } from '../password'

const schema = z.object({
  email: z.string().trim().min(1, 'validation.required').pipe(z.email('validation.email')),
})
type ForgotValues = z.infer<typeof schema>

/** Seconds before "Send again" (the backend also sends at most one email a minute per address). */
const RESEND_AFTER = 60

/**
 * `/forgot-password` (public, `?email=` prefills it): asks for the account's email and sends the reset link.
 * The answer is the same whether or not the address has an account (the backend never tells).
 */
export default function ForgotPasswordPage() {
  const { t } = useTranslation('team')
  const [params] = useSearchParams()
  const forgot = useForgotPassword()
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [cooldown, startCooldown] = useCooldown(RESEND_AFTER)
  const form = useForm<ForgotValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: params.get('email') ?? '' },
  })
  const typed = useWatch({ control: form.control, name: 'email' }) ?? ''

  async function send(email: string) {
    setFailure(null)
    try {
      await forgot.mutateAsync(email)
      setSentTo(email)
      startCooldown()
    } catch (error) {
      setFailure(isThrottled(error) ? t('forgot.throttled') : errorMessage(error, t))
    }
  }

  const scene = (
    <KeySleeve
      account={(sentTo ?? typed).trim()}
      placeholder={t('scene.accountPlaceholder')}
      stamp={sentTo ? <Stamp tone="success">{t('scene.sent')}</Stamp> : undefined}
    />
  )

  return (
    <AccessLayout eyebrow={t('forgot.eyebrow')} scene={scene}>
      {sentTo ? (
        <CheckInbox
          email={sentTo}
          cooldown={cooldown}
          pending={forgot.isPending}
          failure={failure}
          onResend={() => void send(sentTo)}
          onOtherEmail={() => {
            setSentTo(null)
            setFailure(null)
          }}
        />
      ) : (
        <>
          <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-balance text-fg">{t('forgot.title')}</h1>
          <p className="mt-1.5 text-muted">{t('forgot.subtitle')}</p>
          <form onSubmit={form.handleSubmit((values) => send(values.email))} className="mt-8 grid gap-4" noValidate>
            <FormField
              control={form.control}
              name="email"
              label={t('forgot.email')}
              render={({ field, ...a11y }) => (
                <Input
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  placeholder={t('forgot.emailPlaceholder')}
                  className="h-10"
                  autoFocus
                  {...field}
                  {...a11y}
                />
              )}
            />
            {failure && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
                {failure}
              </p>
            )}
            <Button type="submit" variant="primary" size="lg" className="mt-2 w-full" loading={forgot.isPending}>
              {t('forgot.submit')}
            </Button>
          </form>
          <BackToLogin />
        </>
      )}
    </AccessLayout>
  )
}

function CheckInbox({
  email,
  cooldown,
  pending,
  failure,
  onResend,
  onOtherEmail,
}: {
  email: string
  cooldown: number
  pending: boolean
  failure: string | null
  onResend: () => void
  onOtherEmail: () => void
}) {
  const { t } = useTranslation('team')
  const headingRef = useRef<HTMLHeadingElement>(null)
  // The form that had the focus is gone: move it to the new heading so screen readers read what happened.
  useEffect(() => headingRef.current?.focus(), [])

  return (
    <div>
      <span aria-hidden className="grid size-11 place-items-center rounded-xl bg-success-soft text-success-ink">
        <MailCheck className="size-5" />
      </span>
      <h1 ref={headingRef} tabIndex={-1} className="mt-5 text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-fg outline-none">
        {t('forgot.sentTitle')}
      </h1>
      <p className="mt-2 break-words text-muted">{t('forgot.sentText', { email })}</p>
      <ul className="mt-5 grid list-disc gap-1.5 pl-5 text-sm text-muted marker:text-subtle">
        <li>{t('forgot.tipOnce')}</li>
        <li>{t('forgot.tipSpam')}</li>
      </ul>
      {failure && (
        <p role="alert" className="mt-5 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onResend} disabled={cooldown > 0} loading={pending}>
          {cooldown > 0 ? t('forgot.resendIn', { seconds: cooldown }) : t('forgot.resend')}
        </Button>
        <Button variant="ghost" onClick={onOtherEmail}>
          {t('forgot.otherEmail')}
        </Button>
      </div>
      <DevMailboxHint />
      <BackToLogin />
    </div>
  )
}
