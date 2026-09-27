import { Copy, Info, Lock, Plus, Trash2 } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { matchPermission, useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  useCreateRole,
  useDeleteRole,
  useDuplicateRole,
  usePermissionCatalog,
  useRoles,
  useUpdateRole,
  type PermissionModule,
  type Role,
} from '../api'
import { PermissionMatrix } from '../components/PermissionMatrix'
import { PermissionRack } from '../components/PermissionRack'

const NEW = 'new'

export default function RolesPage() {
  const { t } = useTranslation('team')
  const roles = useRoles()
  const catalog = usePermissionCatalog()
  const canManage = useCan('accounts.roles_manage')
  const actorPermissions = useActiveMembership()?.permissions ?? []
  const [selected, setSelected] = useState<string | null>(null)

  if (roles.isError || catalog.isError) {
    return <ErrorState error={roles.error ?? catalog.error} onRetry={() => void Promise.all([roles.refetch(), catalog.refetch()])} />
  }
  if (roles.isPending || catalog.isPending) return <LoadingState />

  const list = roles.data
  const custom = list.filter((role) => !role.is_system)
  const system = list.filter((role) => role.is_system)
  const current = selected === NEW ? null : (list.find((role) => role.id === selected) ?? custom[0] ?? list[0] ?? null)

  return (
    <div>
      <PageHeader
        title={t('roles.title')}
        description={t('roles.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setSelected(NEW)}>
              <Plus aria-hidden />
              {t('roles.new')}
            </Button>
          )
        }
      />
      <div className="grid items-start gap-6 lg:grid-cols-[19rem_1fr]">
        <nav aria-label={t('roles.listLabel')} className="grid gap-5 lg:sticky lg:top-4">
          <RoleGroup title={t('roles.custom')} empty={t('roles.noCustom')}>
            {custom.map((role) => (
              <RoleItem key={role.id} role={role} catalog={catalog.data} active={current?.id === role.id} onSelect={() => setSelected(role.id)} />
            ))}
          </RoleGroup>
          <RoleGroup title={t('roles.system')}>
            {system.map((role) => (
              <RoleItem key={role.id} role={role} catalog={catalog.data} active={current?.id === role.id} onSelect={() => setSelected(role.id)} />
            ))}
          </RoleGroup>
        </nav>
        <RoleEditor
          key={current?.id ?? NEW}
          role={current}
          catalog={catalog.data}
          actorPermissions={actorPermissions}
          canManage={canManage}
          onSelect={setSelected}
        />
      </div>
    </div>
  )
}

function RoleGroup({ title, empty, children }: { title: string; empty?: string; children: ReactNode[] }) {
  return (
    <section className="grid gap-1.5">
      <h2 className="eyebrow px-1">{title}</h2>
      {children.length > 0 ? <ul className="grid gap-1">{children}</ul> : empty && <p className="px-1 text-xs text-muted">{empty}</p>}
    </section>
  )
}

function RoleItem({ role, catalog, active, onSelect }: { role: Role; catalog: PermissionModule[]; active: boolean; onSelect: () => void }) {
  const { t } = useTranslation('team')
  const id = useId()
  // Named by the role alone; the template badge, reach and head count describe it.
  const described = [role.is_system ? `${id}-badge` : null, `${id}-rack`, `${id}-members`].filter(Boolean).join(' ')
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        aria-labelledby={`${id}-name`}
        aria-describedby={described}
        className={cn(
          'grid w-full gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
          active ? 'border-accent/45 bg-accent-soft/50' : 'border-transparent hover:border-border hover:bg-surface',
        )}
      >
        <span className="flex items-center justify-between gap-2">
          <span id={`${id}-name`} className="truncate font-semibold text-fg">
            {role.name}
          </span>
          {role.is_system && (
            <Badge id={`${id}-badge`} tone="neutral">
              {t('roles.systemBadge')}
            </Badge>
          )}
        </span>
        <span className="flex items-center justify-between gap-3">
          <PermissionRack id={`${id}-rack`} name={role.name} value={role.permissions} catalog={catalog} />
          <span id={`${id}-members`} className="num shrink-0 text-xs text-muted">
            {t('roles.members', { count: role.members_count })}
          </span>
        </span>
      </button>
    </li>
  )
}

function RoleEditor({
  role,
  catalog,
  actorPermissions,
  canManage,
  onSelect,
}: {
  role: Role | null
  catalog: PermissionModule[]
  actorPermissions: string[]
  canManage: boolean
  onSelect: (id: string | null) => void
}) {
  const { t } = useTranslation('team')
  const create = useCreateRole()
  const update = useUpdateRole()
  const duplicate = useDuplicateRole()
  const remove = useDeleteRole()
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [permissions, setPermissions] = useState<string[]>(role?.permissions ?? [])
  const [nameError, setNameError] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const editable = canManage && (role ? role.editable : true)
  const canGrant = (code: string) => matchPermission(actorPermissions, code)
  const pending = create.isPending || update.isPending

  async function save(event: FormEvent) {
    event.preventDefault()
    setFailure(null)
    if (!name.trim()) {
      setNameError(t('roles.nameRequired'))
      return
    }
    setNameError(null)
    const payload = { name: name.trim(), description: description.trim(), permissions }
    try {
      if (role) {
        await update.mutateAsync({ id: role.id, ...payload })
        toast.success(t('roles.saved'))
      } else {
        const created = await create.mutateAsync(payload)
        toast.success(t('roles.created'))
        onSelect(created.id)
      }
    } catch (error) {
      if (isApiError(error) && error.fields?.name) setNameError(error.fields.name[0] ?? null)
      setFailure(errorMessage(error, t))
    }
  }

  async function copy() {
    if (!role) return
    try {
      const created = await duplicate.mutateAsync(role.id)
      toast.success(t('roles.duplicated'))
      onSelect(created.id)
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <form onSubmit={save} className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs" noValidate>
      {editable ? (
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="role-name">{t('roles.name')}</Label>
            <Input
              id="role-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={Boolean(nameError)}
              aria-describedby={nameError ? 'role-name-error' : undefined}
            />
            {nameError && (
              <p id="role-name-error" className="text-xs font-medium text-danger-ink">
                {nameError}
              </p>
            )}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="role-description">{t('roles.descriptionLabel')}</Label>
            <Textarea
              id="role-description"
              name="description"
              value={description}
              placeholder={t('roles.descriptionPlaceholder')}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
        </div>
      ) : (
        role && (
          <div>
            <h2 className="flex flex-wrap items-center gap-2 text-lg font-bold text-fg">
              {role.name}
              {role.is_system && <Badge tone="neutral">{t('roles.systemBadge')}</Badge>}
            </h2>
            {role.description && <p className="mt-1 text-sm text-muted">{role.description}</p>}
          </div>
        )
      )}

      {role?.is_system && (
        <p className="flex items-start gap-2 rounded-md bg-info-soft px-3 py-2 text-sm text-info-ink">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('roles.systemHint')}
        </p>
      )}
      {role && !role.is_system && !role.editable && (
        <p className="flex items-start gap-2 rounded-md bg-stone-soft px-3 py-2 text-sm text-stone-ink">
          <Lock aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('roles.locked')}
        </p>
      )}

      <section className="grid gap-3" aria-labelledby="role-permissions">
        <h3 id="role-permissions" className="eyebrow">
          {t('roles.permissions')}
        </h3>
        <PermissionMatrix catalog={catalog} value={permissions} onChange={setPermissions} readOnly={!editable} canGrant={canGrant} />
      </section>

      {failure && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {failure}
        </p>
      )}

      {canManage && (
        <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center">
          {role && !role.is_system && role.editable && (
            <Button variant="ghost" className="text-danger-ink hover:bg-danger-soft sm:mr-auto" onClick={() => setDeleting(true)}>
              <Trash2 aria-hidden />
              {t('roles.delete')}
            </Button>
          )}
          <div className="flex flex-col-reverse gap-2 sm:ml-auto sm:flex-row">
            {role && role.assignable && (
              <Button onClick={copy} loading={duplicate.isPending}>
                <Copy aria-hidden />
                {t('roles.duplicate')}
              </Button>
            )}
            {editable && (
              <Button type="submit" variant="primary" loading={pending}>
                {role ? t('roles.save') : t('roles.create')}
              </Button>
            )}
          </div>
        </div>
      )}

      {role && (
        <ConfirmDialog
          open={deleting}
          onOpenChange={setDeleting}
          title={t('roles.deleteTitle', { name: role.name })}
          description={t('roles.deleteDescription')}
          confirmLabel={t('roles.delete')}
          onConfirm={async () => {
            await remove.mutateAsync(role.id)
            toast.success(t('roles.deleted'))
            onSelect(null)
          }}
        />
      )}
    </form>
  )
}
