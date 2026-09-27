import { Eye, EyeOff, Info, KeyRound } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isApiError } from '@/lib/api'
import { homeFor, useMe } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAcceptInvitation, usePublicInvitation, type PublicInvitation } from '../api'

const MIN_PASSWORD = 8

/** `/invite/:token` (public): someone invited to a team creates their account — or confirms the one they
 * already have — and lands in the app with the role and hotels of the invitation. */
export default function InvitePage() {
  const { token = '' } = useParams()
  const invitation = usePublicInvitation(token)

  if (invitation.isPending) return <LoadingState className="flex-1" />
  if (invitation.isError) {
    if (isApiError(invitation.error) && invitation.error.status === 404) return <ClosedInvitation kind="notFound" />
    return <ErrorState error={invitation.error} onRetry={() => void invitation.refetch()} className="flex-1" />
  }
  if (invitation.data.status === 'expired') return <ClosedInvitation kind="expired" />
  if (invitation.data.status === 'accepted') return <ClosedInvitation kind="used" />
  return <OpenInvitation token={token} invitation={invitation.data} onStale={() => void invitation.refetch()} />
}

function OpenInvitation({ token, invitation, onStale }: { token: string; invitation: PublicInvitation; onStale: () => void }) {
  const { t } = useTranslation('team')
  const organization = invitation.organization.name
  const role = invitation.role.name
  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:gap-16 lg:py-12">
      <section className="flex flex-col rounded-2xl border border-border bg-surface-2 px-6 pt-6 pb-8 sm:px-10 lg:pt-10 lg:pb-10">
        <p className="eyebrow !text-accent-ink">{t('invite.eyebrow')}</p>
        <div className="flex flex-1 items-center justify-center pt-6 lg:pt-12">
          <KeyTag invitation={invitation} />
        </div>
      </section>

      <section className="flex flex-col justify-center">
        <div className="mx-auto w-full max-w-sm">
          <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-balance text-fg">
            {t('invite.title', { organization })}
          </h1>
          <p className="mt-1.5 text-muted">
            {invitation.invited_by
              ? t('invite.invitedBy', { name: invitation.invited_by, role })
              : t('invite.invitedNoName', { role })}
          </p>
          <SignedInNotice email={invitation.email} />
          <AcceptForm token={token} invitation={invitation} onStale={onStale} />
        </div>
      </section>
    </div>
  )
}

/**
 * The invitation drawn as the key tag handed over at the front desk: hung from its ring, with the
 * organization, the role (where the room number would be) and the hotels it opens. It settles once.
 */
function KeyTag({ invitation }: { invitation: PublicInvitation }) {
  const { t, i18n } = useTranslation('team')
  const lang = normalizeLang(i18n.language)
  const organization = invitation.organization.name
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setSettled(true))
    return () => window.cancelAnimationFrame(frame)
  }, [])

  return (
    <div className="relative w-full max-w-[19rem] pt-7">
      <span aria-hidden className="absolute top-0 left-1/2 size-12 -translate-x-1/2 rounded-full border-[3px] border-border-strong" />
      <div
        role="group"
        aria-label={t('invite.tagLabel', { organization })}
        className={cn(
          'relative origin-top rounded-[22px] border border-accent/25 bg-accent-soft px-6 pt-11 pb-5 text-accent-ink shadow-md lg:pt-12 lg:pb-6',
          'transition-transform duration-700 ease-out motion-reduce:transition-none',
          settled ? 'lg:-rotate-2' : 'lg:-rotate-[7deg]',
        )}
      >
        <span
          aria-hidden
          className="absolute top-4 left-1/2 size-4 -translate-x-1/2 rounded-full bg-surface-2 shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)]"
        />
        <p className="eyebrow !text-accent-ink/80">{organization}</p>
        <dl className="mt-1 grid gap-5">
          <div>
            <dt className="sr-only">{t('invite.role')}</dt>
            <dd className="text-[28px] leading-[1.05] font-extrabold tracking-[-0.035em] break-words">{invitation.role.name}</dd>
          </div>
          <div className="border-t border-dashed border-accent/35 pt-4">
            <dt className="eyebrow !text-accent-ink/80">{t('invite.properties')}</dt>
            <dd className="mt-1.5">
              {invitation.all_properties ? (
                <p className="font-semibold">{t('invite.allProperties')}</p>
              ) : (
                <ul className="grid gap-1 font-semibold">
                  {invitation.properties.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        </dl>
        <p className="num mt-6 flex items-center gap-1.5 text-xs text-accent-ink/80">
          <KeyRound aria-hidden className="size-3.5" />
          {t('invite.expires', { date: formatDate(invitation.expires_at, undefined, lang) })}
        </p>
      </div>
    </div>
  )
}

function SignedInNotice({ email }: { email: string }) {
  const { t } = useTranslation('team')
  const { data: me } = useMe()
  if (!me || me.email.toLowerCase() === email.toLowerCase()) return null
  return (
    <p className="mt-5 flex items-start gap-2 rounded-md bg-info-soft px-3 py-2 text-sm text-info-ink">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
      {t('invite.signedInAs', { current: me.email, email })}
    </p>
  )
}

type FieldErrors = { full_name?: string; password?: string }

function AcceptForm({ token, invitation, onStale }: { token: string; invitation: PublicInvitation; onStale: () => void }) {
  const { t } = useTranslation('team')
  const navigate = useNavigate()
  const accept = useAcceptInvitation(token)
  const baseId = useId()
  const existing = invitation.user_exists
  const organization = invitation.organization.name
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [failure, setFailure] = useState<ReactNode>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  function showErrors(found: FieldErrors) {
    setErrors(found)
    // Like the login form: the first field to fix gets the focus.
    if (found.full_name) nameRef.current?.focus()
    else if (found.password) passwordRef.current?.focus()
  }

  function validate(): FieldErrors {
    if (existing) return password ? {} : { password: t('invite.passwordRequired') }
    const found: FieldErrors = {}
    if (!fullName.trim()) found.full_name = t('invite.nameRequired')
    if (password.length < MIN_PASSWORD) found.password = t('invite.passwordTooShort', { min: MIN_PASSWORD })
    return found
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFailure(null)
    const found = validate()
    showErrors(found)
    if (Object.keys(found).length) return
    try {
      const me = await accept.mutateAsync(existing ? { password } : { full_name: fullName.trim(), password })
      toast.success(t('invite.joined', { organization }))
      navigate(homeFor(me), { replace: true })
    } catch (error) {
      if (!isApiError(error)) {
        setFailure(errorMessage(error, t))
      } else if (error.code === 'invalid_credentials') {
        showErrors({ password: t('invite.wrongPassword') })
      } else if (error.code === 'invitation_expired' || error.code === 'invitation_used') {
        onStale() // the page switches to the matching explanation
      } else if (error.code === 'already_member') {
        setFailure(
          <>
            {t('invite.alreadyMember', { organization })}{' '}
            <Link to="/login" className="font-semibold underline underline-offset-4">
              {t('invite.login')}
            </Link>
          </>,
        )
      } else if (error.fields && (error.fields.full_name || error.fields.password)) {
        showErrors({ full_name: error.fields.full_name?.[0], password: error.fields.password?.[0] })
      } else {
        setFailure(errorMessage(error, t))
      }
    }
  }

  const nameId = `${baseId}-name`
  const passwordId = `${baseId}-password`
  const describedBy = (id: string, error: string | undefined, hint = false) =>
    [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(' ') || undefined

  return (
    <form onSubmit={submit} className="mt-8 grid gap-4" noValidate>
      <p className="text-sm text-fg">
        {existing ? t('invite.existing', { email: invitation.email }) : t('invite.newAccount', { email: invitation.email })}
      </p>
      {!existing && (
        <div className="grid gap-1.5">
          <Label htmlFor={nameId}>{t('invite.fullName')}</Label>
          <Input
            ref={nameRef}
            id={nameId}
            name="full_name"
            autoComplete="name"
            className="h-10"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            aria-invalid={Boolean(errors.full_name)}
            aria-describedby={describedBy(nameId, errors.full_name)}
          />
          {errors.full_name && (
            <p id={`${nameId}-error`} className="text-xs font-medium text-danger-ink">
              {errors.full_name}
            </p>
          )}
        </div>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor={passwordId}>{existing ? t('invite.password') : t('invite.newPassword')}</Label>
        <div className="relative">
          <Input
            ref={passwordRef}
            id={passwordId}
            name="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete={existing ? 'current-password' : 'new-password'}
            className="h-10 pr-10"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={describedBy(passwordId, errors.password, !existing && !errors.password)}
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            aria-label={showPassword ? t('invite.hidePassword') : t('invite.showPassword')}
            aria-pressed={showPassword}
            className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-subtle hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {showPassword ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
          </button>
        </div>
        {!existing && !errors.password && (
          <p id={`${passwordId}-hint`} className="text-xs text-muted">
            {t('invite.passwordHint')}
          </p>
        )}
        {errors.password && (
          <p id={`${passwordId}-error`} className="text-xs font-medium text-danger-ink">
            {errors.password}
          </p>
        )}
      </div>
      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}
      <Button type="submit" variant="primary" size="lg" className="mt-2 w-full" loading={accept.isPending}>
        {t('invite.submit', { organization })}
      </Button>
    </form>
  )
}

const CLOSED = {
  expired: { title: 'invite.expiredTitle', text: 'invite.expiredText' },
  used: { title: 'invite.usedTitle', text: 'invite.usedText' },
  notFound: { title: 'invite.notFoundTitle', text: 'invite.notFoundText' },
} as const

/** A link that no longer opens anything: say why and where to go instead. */
function ClosedInvitation({ kind }: { kind: keyof typeof CLOSED }) {
  const { t } = useTranslation('team')
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-4 py-16 text-center">
      <span aria-hidden className="relative grid size-16 place-items-center rounded-2xl border border-dashed border-border-strong bg-surface-2 text-subtle">
        <span className="absolute top-2 left-2 size-2 rounded-full bg-bg shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]" />
        <KeyRound className="size-6" />
      </span>
      <h1 className="mt-6 text-[24px] leading-tight font-extrabold tracking-[-0.03em] text-fg">{t(CLOSED[kind].title)}</h1>
      <p className="mt-2 text-muted">{t(CLOSED[kind].text)}</p>
      <Button asChild variant="primary" className="mt-6">
        <Link to="/login">{t('invite.login')}</Link>
      </Button>
    </div>
  )
}
