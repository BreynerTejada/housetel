import type { ColumnDef } from '@tanstack/react-table'
import { Copy, EllipsisVertical, Lock, Mail, RotateCw, UserCheck, UserPlus, UserX, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DataTable } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Avatar, AvatarFallback, initials } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip } from '@/components/ui/tooltip'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatRelative, normalizeLang } from '@/lib/format'
import {
  useInvitations,
  useMembers,
  useResendInvitation,
  useRevokeInvitation,
  useRoles,
  useUpdateMember,
  type Invitation,
  type Member,
} from '../api'
import { InviteDialog } from '../components/InviteDialog'
import { MemberDialog } from '../components/MemberDialog'

export default function UsersPage() {
  const { t, i18n } = useTranslation('team')
  const lang = normalizeLang(i18n.language)
  const membership = useActiveMembership()
  const properties = membership?.properties ?? []
  const members = useMembers()
  const invitations = useInvitations()
  const roles = useRoles()
  const updateMember = useUpdateMember()
  const [inviting, setInviting] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)
  const [deactivating, setDeactivating] = useState<Member | null>(null)
  // Someone who only works in some hotels can only give access to those hotels (the backend enforces it).
  const restricted = members.data?.results.some((member) => member.is_self && !member.all_properties) ?? false

  async function reactivate(member: Member) {
    try {
      await updateMember.mutateAsync({ id: member.id, is_active: true })
      toast.success(t('users.reactivated'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  const columns: ColumnDef<Member>[] = [
    {
      id: 'person',
      accessorFn: (member) => `${member.user.full_name} ${member.user.email}`,
      header: t('users.columns.person'),
      cell: ({ row }) => {
        const { user, is_self: isSelf, is_active: active } = row.original
        return (
          <div className="flex min-w-0 items-center gap-3">
            <Avatar className={active ? '' : 'opacity-50'}>
              <AvatarFallback>{initials(user.full_name, user.email)}</AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5">
                <span className="truncate font-semibold text-fg">{user.full_name || user.email}</span>
                {isSelf && <Badge tone="outline">{t('users.you')}</Badge>}
              </p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
          </div>
        )
      },
    },
    {
      id: 'role',
      accessorFn: (member) => member.role.name,
      header: t('users.columns.role'),
      cell: ({ row }) => <Badge tone={row.original.is_owner ? 'accent' : 'neutral'}>{row.original.role.name}</Badge>,
    },
    {
      id: 'properties',
      header: t('users.columns.properties'),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.all_properties ? (
          <span className="text-[13px] text-muted">{t('users.allProperties')}</span>
        ) : (
          <span className="text-[13px] text-fg">{row.original.properties.map((property) => property.name).join(', ')}</span>
        ),
    },
    {
      id: 'status',
      accessorFn: (member) => (member.is_active ? 1 : 0),
      header: t('users.columns.status'),
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge tone="success">{t('users.active')}</Badge>
        ) : (
          <Badge tone="stone">{t('users.inactive')}</Badge>
        ),
    },
    {
      id: 'lastLogin',
      header: t('users.columns.lastLogin'),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-[13px] text-muted">
          {row.original.user.last_login ? formatRelative(row.original.user.last_login, lang) : t('users.never')}
        </span>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">{t('users.columns.actions')}</span>,
      enableSorting: false,
      meta: { align: 'right' },
      cell: ({ row }) => {
        const member = row.original
        const name = member.user.full_name || member.user.email
        if (member.is_self) return null
        if (!member.editable) {
          return (
            <Tooltip content={t('users.locked')}>
              <span
                tabIndex={0}
                aria-label={t('users.locked')}
                className="inline-grid size-8 place-items-center rounded-md text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <Lock aria-hidden className="size-4" />
              </span>
            </Tooltip>
          )
        }
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={t('users.actions', { name })}>
                <EllipsisVertical aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setEditing(member)}>
                <UserCheck aria-hidden />
                {t('users.edit')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {member.is_active ? (
                <DropdownMenuItem destructive onSelect={() => setDeactivating(member)}>
                  <UserX aria-hidden />
                  {t('users.deactivate')}
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onSelect={() => void reactivate(member)}>
                  <UserCheck aria-hidden />
                  {t('users.reactivate')}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  if (members.isError) return <ErrorState error={members.error} onRetry={() => void members.refetch()} />

  return (
    // grid-cols-1 = minmax(0, 1fr): the column never grows to the table's width, which scrolls inside its card.
    <div className="grid grid-cols-1 gap-8">
      <div>
        <PageHeader
          title={t('users.title')}
          description={t('users.description')}
          actions={
            <Button variant="primary" onClick={() => setInviting(true)}>
              <UserPlus aria-hidden />
              {t('users.invite')}
            </Button>
          }
        />
        <DataTable
          aria-label={t('users.tableLabel')}
          columns={columns}
          data={members.data?.results ?? []}
          getRowId={(member) => member.id}
          isLoading={members.isPending}
          enableSearch
          searchPlaceholder={t('users.search')}
          pageSize={50}
        />
      </div>

      {(invitations.data?.length ?? 0) > 0 && <PendingInvitations invitations={invitations.data ?? []} />}

      <InviteDialog open={inviting} onOpenChange={setInviting} roles={roles.data ?? []} properties={properties} restricted={restricted} />
      <MemberDialog
        member={editing}
        onOpenChange={(open) => !open && setEditing(null)}
        roles={roles.data ?? []}
        properties={properties}
        restricted={restricted}
      />
      <ConfirmDialog
        open={Boolean(deactivating)}
        onOpenChange={(open) => !open && setDeactivating(null)}
        title={t('users.deactivateTitle', { name: deactivating?.user.full_name || deactivating?.user.email })}
        description={t('users.deactivateDescription')}
        confirmLabel={t('users.deactivate')}
        onConfirm={async () => {
          if (!deactivating) return
          await updateMember.mutateAsync({ id: deactivating.id, is_active: false })
          toast.success(t('users.deactivated'))
        }}
      />
    </div>
  )
}

function PendingInvitations({ invitations }: { invitations: Invitation[] }) {
  const { t, i18n } = useTranslation('team')
  const lang = normalizeLang(i18n.language)
  const resend = useResendInvitation()
  const revoke = useRevokeInvitation()
  const [revoking, setRevoking] = useState<Invitation | null>(null)

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t('invitations.copied'))
    } catch {
      toast.error(url)
    }
  }

  async function sendAgain(invitation: Invitation) {
    try {
      const sent = await resend.mutateAsync(invitation.id)
      if (sent.email_sent === false) toast.warning(t('invitations.emailFailed'))
      else toast.success(t('invitations.resent', { email: invitation.email }))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <section aria-labelledby="pending-invitations" className="grid gap-3">
      <div>
        <h2 id="pending-invitations" className="text-base font-bold text-fg">
          {t('invitations.title')}
        </h2>
        <p className="text-sm text-muted">{t('invitations.description')}</p>
      </div>
      <ul className="grid gap-2">
        {invitations.map((invitation) => {
          const expired = invitation.status === 'expired'
          return (
            <li
              key={invitation.id}
              className="flex flex-col gap-3 rounded-lg border border-dashed border-border-strong bg-surface p-3 sm:flex-row sm:items-center"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
                <Mail aria-hidden className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-semibold text-fg">{invitation.email}</span>
                  <Badge>{invitation.role.name}</Badge>
                  {expired && <Badge tone="warning">{t('invitations.expired', { date: formatDate(invitation.expires_at, undefined, lang) })}</Badge>}
                </p>
                <p className="text-xs text-muted">
                  {[
                    invitation.all_properties ? t('users.allProperties') : invitation.properties.map((p) => p.name).join(', '),
                    expired ? null : t('invitations.expires', { date: formatRelative(invitation.expires_at, lang) }),
                    invitation.invited_by ? t('invitations.invitedBy', { name: invitation.invited_by.full_name || invitation.invited_by.email }) : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {invitation.editable ? (
                  <>
                    {invitation.invite_url && (
                      <Button size="sm" variant="ghost" onClick={() => void copy(invitation.invite_url ?? '')}>
                        <Copy aria-hidden />
                        {t('invitations.copy')}
                      </Button>
                    )}
                    <Button size="sm" onClick={() => void sendAgain(invitation)} loading={resend.isPending && resend.variables === invitation.id}>
                      <RotateCw aria-hidden />
                      {t('invitations.resend')}
                    </Button>
                    <Button size="sm" variant="ghost" className="text-danger-ink hover:bg-danger-soft" onClick={() => setRevoking(invitation)}>
                      <X aria-hidden />
                      {t('invitations.revoke')}
                    </Button>
                  </>
                ) : (
                  // Sent by someone with wider access (role or hotels): only they can resend or revoke it.
                  <Tooltip content={t('invitations.locked')}>
                    <span
                      tabIndex={0}
                      aria-label={t('invitations.locked')}
                      className="inline-grid size-8 place-items-center rounded-md text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      <Lock aria-hidden className="size-4" />
                    </span>
                  </Tooltip>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={t('invitations.revokeTitle', { email: revoking?.email })}
        description={t('invitations.revokeDescription')}
        confirmLabel={t('invitations.revoke')}
        onConfirm={async () => {
          if (!revoking) return
          await revoke.mutateAsync(revoking.id)
          toast.success(t('invitations.revoked'))
        }}
      />
    </section>
  )
}
