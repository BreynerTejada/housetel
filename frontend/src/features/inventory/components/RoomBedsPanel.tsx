import { useMutation } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useBeds, useInvalidateInventory, type Bed, type BedType, type Room } from '../api'
import { naturalCompare } from '../lib/text'

const BED_TYPES: BedType[] = ['single', 'bunk_bottom', 'bunk_top', 'double']

/** Sellable beds of a dorm room: each one is a unit of inventory. */
export function RoomBedsPanel({ room, canEdit }: { room: Room; canEdit: boolean }) {
  const { t } = useTranslation('inventory')
  const beds = useBeds(room.id)
  const invalidate = useInvalidateInventory()
  const [count, setCount] = useState(2)
  const [prefix, setPrefix] = useState('C')
  const countId = useId()
  const prefixId = useId()

  const onError = (error: unknown) => toast.error(errorMessage(error, t))
  const update = useMutation({
    mutationFn: ({ bed, changes }: { bed: Bed; changes: Partial<Bed> }) =>
      api.patch<Bed>(`/inventory/rooms/${room.id}/beds/${bed.id}/`, changes),
    onSuccess: () => void invalidate(),
    onError,
  })
  const remove = useMutation({
    mutationFn: (bed: Bed) => api.delete(`/inventory/rooms/${room.id}/beds/${bed.id}/`),
    onSuccess: () => {
      toast.success(t('beds.deleted'))
      void invalidate()
    },
  })
  const addMany = useMutation({
    mutationFn: () => api.post<Bed[]>(`/inventory/rooms/${room.id}/beds/bulk/`, { count, prefix, bed_type: 'bunk' }),
    onSuccess: (created) => {
      toast.success(t('beds.added', { count: created.length }))
      void invalidate()
    },
    onError,
  })

  if (beds.isError) return <ErrorState error={beds.error} onRetry={() => void beds.refetch()} />
  if (!beds.data) return <LoadingState variant="rows" rows={3} />
  const list = [...beds.data].sort((a, b) => naturalCompare(a.label, b.label))
  const active = list.filter((bed) => bed.is_active).length

  return (
    <div className="grid gap-4">
      <p className="max-w-2xl text-sm text-muted">{t('beds.hint', { active, total: list.length })}</p>
      {list.length === 0 ? (
        <EmptyState title={t('beds.emptyTitle')} description={t('beds.emptyDescription')} />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((bed) => (
            <li key={bed.id} className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 shadow-xs">
              <span className="num w-10 font-bold text-fg">{bed.label}</span>
              <Select
                name={`bed.${bed.label}.type`}
                value={bed.bed_type}
                disabled={!canEdit}
                onValueChange={(value) => update.mutate({ bed, changes: { bed_type: value as BedType } })}
              >
                <SelectTrigger className="h-8 min-w-0 flex-1" aria-label={t('beds.typeOfBed', { label: bed.label })}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BED_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {t(`sellableBedTypes.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Switch
                name={`bed.${bed.label}.active`}
                aria-label={t('beds.activeBed', { label: bed.label })}
                checked={bed.is_active}
                disabled={!canEdit}
                onCheckedChange={(checked) => update.mutate({ bed, changes: { is_active: checked } })}
              />
              {canEdit && (
                <ConfirmDialog
                  title={t('beds.deleteTitle', { label: bed.label })}
                  description={t('beds.deleteDescription')}
                  confirmLabel={t('common:actions.delete')}
                  onConfirm={() => remove.mutateAsync(bed)}
                  trigger={
                    <Button variant="ghost" size="icon-sm" aria-label={t('beds.deleteBed', { label: bed.label })}>
                      <Trash2 aria-hidden />
                    </Button>
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-lg border border-dashed border-border-strong p-3"
          onSubmit={(event) => {
            event.preventDefault()
            addMany.mutate()
          }}
        >
          <label className="grid gap-1" htmlFor={countId}>
            <span className="text-[13px] font-semibold">{t('beds.count')}</span>
            <Input id={countId} name="count" type="number" min={1} max={50} className="w-24" value={count}
                   onChange={(event) => setCount(event.target.valueAsNumber || 1)} />
          </label>
          <label className="grid gap-1" htmlFor={prefixId}>
            <span className="text-[13px] font-semibold">{t('beds.prefix')}</span>
            <Input id={prefixId} name="prefix" maxLength={10} className="w-24" value={prefix} onChange={(event) => setPrefix(event.target.value)} />
          </label>
          <Button type="submit" loading={addMany.isPending}>
            <Plus aria-hidden />
            {t('beds.addMany')}
          </Button>
          <p className="basis-full text-xs text-muted">{t('beds.addManyHint')}</p>
        </form>
      )}
    </div>
  )
}
