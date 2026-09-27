import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { PropertySummary } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useUpdateMember, type Member, type Role } from '../api'
import { AccessFields, type AccessValue } from './AccessFields'

/** Change the role and hotels of a team member. */
export function MemberDialog({
  member,
  onOpenChange,
  roles,
  properties,
  restricted = false,
}: {
  member: Member | null
  onOpenChange: (open: boolean) => void
  roles: Role[]
  /** Hotels the current user can give access to. */
  properties: PropertySummary[]
  /** The current user only works in some hotels: no "all hotels" option. */
  restricted?: boolean
}) {
  const [pending, setPending] = useState(false)
  return (
    <Dialog open={Boolean(member)} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-lg" hideClose={pending}>
        {member && (
          <MemberForm
            member={member}
            roles={roles}
            properties={properties}
            restricted={restricted}
            onPendingChange={setPending}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function MemberForm({
  member,
  roles,
  properties,
  restricted,
  onPendingChange,
  onClose,
}: {
  member: Member
  roles: Role[]
  properties: PropertySummary[]
  restricted: boolean
  onPendingChange: (pending: boolean) => void
  onClose: () => void
}) {
  const { t } = useTranslation('team')
  const update = useUpdateMember()
  const [access, setAccess] = useState<AccessValue>({
    roleId: member.role.id,
    allProperties: member.all_properties,
    propertyIds: member.properties.map((property) => property.id),
  })
  const [failure, setFailure] = useState<string | null>(null)
  const [propertiesError, setPropertiesError] = useState<string | null>(null)
  const name = member.user.full_name || member.user.email

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFailure(null)
    if (!access.allProperties && access.propertyIds.length === 0) {
      setPropertiesError(t('inviteDialog.propertiesRequired'))
      return
    }
    setPropertiesError(null)
    onPendingChange(true)
    try {
      await update.mutateAsync({
        id: member.id,
        role_id: access.roleId,
        all_properties: access.allProperties,
        property_ids: access.allProperties ? [] : access.propertyIds,
      })
      onPendingChange(false)
      toast.success(t('memberDialog.saved'))
      onClose()
    } catch (error) {
      onPendingChange(false)
      setFailure(errorMessage(error, t))
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <DialogHeader>
        <DialogTitle>{t('memberDialog.title', { name })}</DialogTitle>
        <DialogDescription>{t('memberDialog.description')}</DialogDescription>
      </DialogHeader>
      <AccessFields
        value={access}
        onChange={setAccess}
        roles={roles}
        properties={properties}
        propertiesError={propertiesError}
        allowAll={!restricted}
      />
      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}
      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={update.isPending}>
          {t('actions.cancel', { ns: 'common' })}
        </Button>
        <Button type="submit" variant="primary" loading={update.isPending}>
          {t('memberDialog.save')}
        </Button>
      </DialogFooter>
    </form>
  )
}
