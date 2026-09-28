import { Pencil, Plus, SlidersHorizontal, Trash } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useDeleteRule, useRevenueOptions, useRules, useSaveRule, type PricingRule, type RevenueOptions } from '../api'
import { pick } from '../lib/format'
import { KindIcon } from './KindIcon'
import { RuleEditorSheet } from './RuleEditorSheet'
import { RuleVisual } from './RuleVisual'

/** The pricing rules of the property as cards (each drawn for its kind), with the editor and quick on/off. */
export function RulesPanel({ today }: { today: string }) {
  const { t } = useTranslation('revenue')
  const canManage = useCan('revenue.manage')
  const rules = useRules()
  const options = useRevenueOptions()
  const [editing, setEditing] = useState<PricingRule | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<PricingRule | null>(null)
  const remove = useDeleteRule()

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">{t('rules.intro')}</p>
        {canManage && (
          <Button variant="primary" onClick={() => setEditing(null)}>
            <Plus aria-hidden />
            {t('rules.new')}
          </Button>
        )}
      </div>

      {rules.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : rules.isError ? (
        <ErrorState error={rules.error} onRetry={() => void rules.refetch()} />
      ) : rules.data.length === 0 ? (
        <EmptyState
          icon={SlidersHorizontal}
          title={t('rules.emptyTitle')}
          description={t('rules.emptyHint')}
          action={
            canManage && (
              <Button variant="primary" onClick={() => setEditing(null)}>
                <Plus aria-hidden />
                {t('rules.new')}
              </Button>
            )
          }
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {rules.data.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              options={options.data}
              canManage={canManage}
              onEdit={() => setEditing(rule)}
              onDelete={() => setDeleting(rule)}
            />
          ))}
        </div>
      )}

      <RuleEditorSheet rule={editing} options={options.data} today={today} onClose={() => setEditing(undefined)} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('rules.deleteTitle', { name: deleting?.name ?? '' })}
        description={t('rules.deleteHint')}
        confirmLabel={t('rules.deleteConfirm')}
        onConfirm={async () => {
          if (!deleting) return
          await remove.mutateAsync(deleting.id)
          toast.success(t('rules.deleted'))
        }}
      />
    </div>
  )
}

function RuleCard({
  rule,
  options,
  canManage,
  onEdit,
  onDelete,
}: {
  rule: PricingRule
  options: RevenueOptions | undefined
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const save = useSaveRule()
  const roomTypes = new Map((options?.room_types ?? []).map((roomType) => [roomType.id, roomType]))

  function toggle(active: boolean) {
    save.mutate(
      { id: rule.id, body: { is_active: active } },
      {
        onSuccess: () => toast.success(t(active ? 'rules.activated' : 'rules.deactivated')),
        onError: (error) => toast.error(errorMessage(error, t)),
      },
    )
  }

  return (
    <article aria-labelledby={titleId} className={cn('grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs', !rule.is_active && 'bg-surface-2/40')}>
      <header className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-border bg-surface-2 text-muted">
          <KindIcon kind={rule.kind} className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className={cn('truncate text-[15px] leading-6 font-bold', rule.is_active ? 'text-fg' : 'text-muted')}>
            {rule.name}
          </h3>
          <p className="text-xs text-muted">{t(`rules.kinds.${rule.kind}`)}</p>
        </div>
        <Switch
          checked={rule.is_active}
          aria-label={t('rules.toggle', { name: rule.name })}
          disabled={!canManage || save.isPending}
          onCheckedChange={toggle}
        />
      </header>
      <div className={cn(!rule.is_active && 'opacity-60')}>
        <RuleVisual rule={rule} />
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted">
        <Badge tone={rule.combine === 'max' ? 'info' : 'neutral'}>{t(`rules.combine.${rule.combine}`)}</Badge>
        <span className="num">{t('rules.priority', { value: rule.priority })}</span>
        <span aria-hidden>·</span>
        {rule.room_types.length === 0 ? (
          <span>{t('rules.allRoomTypes')}</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {rule.room_types.map((id) => {
              const roomType = roomTypes.get(id)
              return (
                <span key={id} title={roomType ? pick(roomType.name, lang) : undefined} className="rounded bg-surface-2 px-1.5 py-px font-semibold text-fg">
                  {roomType?.code ?? '—'}
                </span>
              )
            })}
          </span>
        )}
        {!rule.is_active && <Badge tone="stone">{t('rules.inactive')}</Badge>}
        {canManage && (
          <span className="ml-auto flex gap-1">
            <Button variant="ghost" size="icon-sm" aria-label={t('rules.edit', { name: rule.name })} onClick={onEdit}>
              <Pencil aria-hidden />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={t('rules.delete', { name: rule.name })} onClick={onDelete}>
              <Trash aria-hidden />
            </Button>
          </span>
        )}
      </footer>
    </article>
  )
}
