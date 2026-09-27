import { Copy, TriangleAlert } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isApiError } from '@/lib/api'
import type { PropertySummary } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useInviteMember, type Invitation, type Role } from '../api'
import { AccessFields, type AccessValue } from './AccessFields'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function InviteDialog({
  open,
  onOpenChange,
  roles,
  properties,
  restricted = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  roles: Role[]
  /** Hotels the current user can give access to. */
  properties: PropertySummary[]
  /** The current user only works in some hotels: no "all hotels" option. */
  restricted?: boolean
}) {
  const [pending, setPending] = useState(false)
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-lg" hideClose={pending}>
        {/* A fresh form on every opening. */}
        <InviteForm
          roles={roles}
          properties={properties}
          restricted={restricted}
          onPendingChange={setPending}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function InviteForm({
  roles,
  properties,
  restricted,
  onPendingChange,
  onClose,
}: {
  roles: Role[]
  properties: PropertySummary[]
  restricted: boolean
  onPendingChange: (pending: boolean) => void
  onClose: () => void
}) {
  const { t } = useTranslation('team')
  const invite = useInviteMember()
  const [email, setEmail] = useState('')
  const [access, setAccess] = useState<AccessValue>(() => ({
    roleId: '',
    allProperties: !restricted,
    // Someone who works in a single hotel invites to that hotel.
    propertyIds: restricted && properties.length === 1 ? properties.map((property) => property.id) : [],
  }))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [unsent, setUnsent] = useState<Invitation | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const found: Record<string, string> = {}
    if (!EMAIL.test(email.trim())) found.email = t('validation.email', { ns: 'common' })
    if (!access.roleId) found.role_id = t('validation.required', { ns: 'common' })
    if (!access.allProperties && access.propertyIds.length === 0) found.property_ids = t('inviteDialog.propertiesRequired')
    setErrors(found)
    setFailure(null)
    if (Object.keys(found).length) return
    onPendingChange(true)
    try {
      const invitation = await invite.mutateAsync({
        email: email.trim(),
        role_id: access.roleId,
        all_properties: access.allProperties,
        property_ids: access.allProperties ? [] : access.propertyIds,
      })
      onPendingChange(false)
      if (invitation.email_sent === false) {
        setUnsent(invitation)
        return
      }
      toast.success(t('inviteDialog.sent', { email: invitation.email }))
      onClose()
    } catch (error) {
      onPendingChange(false)
      if (isApiError(error) && error.fields) {
        setErrors(Object.fromEntries(Object.entries(error.fields).map(([field, messages]) => [field, messages[0] ?? ''])))
      }
      setFailure(errorMessage(error, t))
    }
  }

  if (unsent?.invite_url) {
    return (
      <div className="grid gap-4">
        <DialogHeader>
          <DialogTitle>{t('inviteDialog.title')}</DialogTitle>
          <DialogDescription>{t('inviteDialog.description')}</DialogDescription>
        </DialogHeader>
        <p role="alert" className="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('invitations.emailFailed')}
        </p>
        <CopyLink url={unsent.invite_url} />
        <DialogFooter>
          <Button variant="primary" onClick={onClose}>
            {t('actions.close', { ns: 'common' })}
          </Button>
        </DialogFooter>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <DialogHeader>
        <DialogTitle>{t('inviteDialog.title')}</DialogTitle>
        <DialogDescription>{t('inviteDialog.description')}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label htmlFor="invite-email">{t('inviteDialog.email')}</Label>
        <Input
          id="invite-email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="off"
          placeholder={t('inviteDialog.emailPlaceholder')}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? 'invite-email-error' : undefined}
        />
        {errors.email && (
          <p id="invite-email-error" className="text-xs font-medium text-danger-ink">
            {errors.email}
          </p>
        )}
      </div>
      <AccessFields
        value={access}
        onChange={setAccess}
        roles={roles}
        properties={properties}
        propertiesError={errors.property_ids}
        allowAll={!restricted}
      />
      {errors.role_id && <p className="-mt-2 text-xs font-medium text-danger-ink">{errors.role_id}</p>}
      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}
      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={invite.isPending}>
          {t('actions.cancel', { ns: 'common' })}
        </Button>
        <Button type="submit" variant="primary" loading={invite.isPending}>
          {t('inviteDialog.send')}
        </Button>
      </DialogFooter>
    </form>
  )
}

/** Read-only link + copy button (invitations can also be shared by WhatsApp or chat). */
export function CopyLink({ url }: { url: string }) {
  const { t } = useTranslation('team')
  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t('invitations.copied'))
    } catch {
      /* clipboard unavailable: the field stays selectable */
    }
  }
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="invite-link">{t('inviteDialog.linkLabel')}</Label>
      <div className="flex gap-2">
        <Input id="invite-link" readOnly value={url} className="num text-xs" onFocus={(event) => event.currentTarget.select()} />
        <Button variant="secondary" onClick={copy}>
          <Copy aria-hidden />
          {t('invitations.copy')}
        </Button>
      </div>
    </div>
  )
}
