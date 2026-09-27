import { useMutation } from '@tanstack/react-query'
import { PencilLine, Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useCan } from '@/lib/permissions'
import {
  CUSTOM_FIELD_TARGETS,
  useCustomFields,
  useInvalidateInventory,
  type CustomFieldDefinition,
  type CustomFieldTarget,
} from '../api'
import { CustomFieldDialog } from '../components/CustomFieldDialog'
import { tr } from '../lib/text'

/** Fields each hotel defines for its categories, rooms, guests and reservations. */
export default function CustomFieldsPage() {
  const { t } = useTranslation('inventory')
  const canManage = useCan('inventory.manage')
  const fields = useCustomFields()
  const [dialog, setDialog] = useState<{ definition?: CustomFieldDefinition; target: CustomFieldTarget } | null>(null)

  return (
    <>
      <PageHeader
        title={t('nav.customFields')}
        description={t('customFields.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setDialog({ target: 'room_type' })}>
              <Plus aria-hidden />
              {t('customFields.new')}
            </Button>
          )
        }
      />
      {fields.isError ? (
        <ErrorState error={fields.error} onRetry={() => void fields.refetch()} />
      ) : !fields.data ? (
        <LoadingState variant="rows" rows={4} />
      ) : fields.data.length === 0 ? (
        <EmptyState icon={SlidersHorizontal} title={t('customFields.emptyTitle')} description={t('customFields.emptyDescription')} />
      ) : (
        <div className="grid gap-6">
          {CUSTOM_FIELD_TARGETS.map((target) => (
            <TargetSection
              key={target}
              target={target}
              definitions={fields.data.filter((definition) => definition.applies_to === target)}
              canManage={canManage}
              onAdd={() => setDialog({ target })}
              onEdit={(definition) => setDialog({ definition, target })}
            />
          ))}
        </div>
      )}
      {dialog && (
        <CustomFieldDialog
          key={dialog.definition?.id ?? `new-${dialog.target}`}
          definition={dialog.definition}
          defaultTarget={dialog.target}
          open
          onOpenChange={(open) => !open && setDialog(null)}
        />
      )}
    </>
  )
}

function TargetSection({
  target,
  definitions,
  canManage,
  onAdd,
  onEdit,
}: {
  target: CustomFieldTarget
  definitions: CustomFieldDefinition[]
  canManage: boolean
  onAdd: () => void
  onEdit: (definition: CustomFieldDefinition) => void
}) {
  const { t, i18n } = useTranslation('inventory')
  const invalidate = useInvalidateInventory()
  const headingId = `custom-fields-${target}`
  const remove = useMutation({
    mutationFn: (definition: CustomFieldDefinition) => api.delete(`/inventory/custom-fields/${definition.id}/`),
    onSuccess: () => {
      toast.success(t('customFields.deleted'))
      void invalidate()
    },
  })

  return (
    <section role="region" aria-labelledby={headingId} className="grid gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 id={headingId} className="text-[15px] text-fg">
            {t(`targets.${target}`)}
          </h2>
          <p className="text-[13px] text-muted">{t(`customFields.targetHint.${target}`)}</p>
        </div>
        {canManage && (
          <Button variant="ghost" size="sm" onClick={onAdd} aria-label={t('customFields.addTo', { target: t(`targets.${target}`) })}>
            <Plus aria-hidden />
            {t('common:actions.add')}
          </Button>
        )}
      </div>
      {definitions.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted">{t('customFields.noneFor')}</p>
      ) : (
        <ul className="divide-y divide-border/70 rounded-lg border border-border bg-surface shadow-xs">
          {definitions.map((definition) => {
            const label = tr(definition.label, i18n.language)
            const type = t(`fieldTypes.${definition.field_type}`)
            const summary =
              definition.field_type === 'select' || definition.field_type === 'multiselect'
                ? `${type} · ${t('customFields.optionsCount', { count: definition.options.length })}`
                : type
            return (
              <li key={definition.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
                <div className="grid min-w-0 flex-1">
                  <span className="font-semibold text-fg">{label}</span>
                  <span className="text-xs text-muted">
                    <code className="num">{definition.key}</code>
                  </span>
                </div>
                <span className="text-[13px] text-muted">{summary}</span>
                <span className="flex flex-wrap gap-1.5">
                  {definition.required && <Badge tone="warning">{t('customFields.requiredBadge')}</Badge>}
                  {definition.show_in_marketplace && <Badge tone="info">{t('customFields.marketplaceBadge')}</Badge>}
                  <Badge tone="outline">{t(`customFields.scopes.${definition.scope}`)}</Badge>
                </span>
                {canManage && (
                  <span className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-sm" aria-label={t('customFields.edit', { label })} onClick={() => onEdit(definition)}>
                      <PencilLine aria-hidden />
                    </Button>
                    <ConfirmDialog
                      title={t('customFields.deleteTitle', { label })}
                      description={t(target === 'guest' || target === 'reservation' ? 'customFields.deleteOther' : 'customFields.deleteInventory')}
                      confirmLabel={t('common:actions.delete')}
                      onConfirm={() => remove.mutateAsync(definition)}
                      trigger={
                        <Button variant="ghost" size="icon-sm" aria-label={t('customFields.delete', { label })}>
                          <Trash2 aria-hidden />
                        </Button>
                      }
                    />
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
