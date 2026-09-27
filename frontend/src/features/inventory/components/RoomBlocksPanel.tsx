import { useMutation } from '@tanstack/react-query'
import { Ban, CalendarX2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useActiveProperty } from '@/lib/auth'
import { formatDateRange, nightsBetween, normalizeLang } from '@/lib/format'
import { useBlocks, useInvalidateInventory, type Room, type RoomBlock } from '../api'
import { BlockDialog } from './BlockDialog'

/** Blocks of one room: current and upcoming first (can be released), then the history. */
export function RoomBlocksPanel({ room, canEdit }: { room: Room; canEdit: boolean }) {
  const { t, i18n } = useTranslation('inventory')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const blocks = useBlocks({ room: room.id })
  const invalidate = useInvalidateInventory()
  const [open, setOpen] = useState(false)

  const release = useMutation({
    mutationFn: (block: RoomBlock) => api.post<RoomBlock>(`/inventory/blocks/${block.id}/release/`),
    onSuccess: () => {
      toast.success(t('blocks.released'))
      void invalidate()
    },
  })

  if (blocks.isError) return <ErrorState error={blocks.error} onRetry={() => void blocks.refetch()} />
  if (!blocks.data) return <LoadingState variant="rows" rows={3} />

  const today = property?.business_date ?? ''
  const all = blocks.data.results
  const current = all.filter((block) => block.is_active && block.end_date > today)
  const history = all.filter((block) => !current.includes(block)).reverse()

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-muted">{t('blocks.hint')}</p>
        {canEdit && (
          <Button onClick={() => setOpen(true)}>
            <Ban aria-hidden />
            {t('blocks.new')}
          </Button>
        )}
      </div>

      {current.length === 0 ? (
        <EmptyState icon={CalendarX2} title={t('blocks.emptyTitle')} description={t('blocks.emptyDescription')} />
      ) : (
        <ul className="grid gap-2">
          {current.map((block) => (
            <li key={block.id} className="hatch flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-surface px-4 py-3">
              <Badge tone="stone">{t(`blockKinds.${block.kind}`)}</Badge>
              <span className="num font-semibold text-fg">
                {formatDateRange(block.start_date, block.end_date, lang)}
                <span className="ml-2 font-normal text-muted">{t('common:date.nights', { count: nightsBetween(block.start_date, block.end_date) })}</span>
              </span>
              {block.bed_label && <span className="text-sm text-muted">{t('blocks.bedLabel', { label: block.bed_label })}</span>}
              {block.reason && <span className="min-w-0 flex-1 truncate text-sm text-muted">{block.reason}</span>}
              {canEdit && (
                <ConfirmDialog
                  title={t('blocks.releaseTitle', { number: room.number })}
                  description={t('blocks.releaseDescription')}
                  confirmLabel={t('blocks.release')}
                  onConfirm={() => release.mutateAsync(block)}
                  trigger={
                    <Button variant="secondary" size="sm" className="ml-auto">
                      {t('blocks.release')}
                    </Button>
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {history.length > 0 && (
        <section aria-labelledby="blocks-history" className="grid gap-2">
          <h3 id="blocks-history" className="eyebrow">
            {t('blocks.history')}
          </h3>
          <ul className="divide-y divide-border/70 rounded-lg border border-border bg-surface px-4 text-sm">
            {history.map((block) => (
              <li key={block.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-muted">
                <span className="num">{formatDateRange(block.start_date, block.end_date, lang)}</span>
                <span>{t(`blockKinds.${block.kind}`)}</span>
                {block.reason && <span className="truncate">{block.reason}</span>}
                <span className="ml-auto text-xs">{block.released_at ? t('blocks.wasReleased') : t('blocks.finished')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {canEdit && <BlockDialog room={room} open={open} onOpenChange={setOpen} />}
    </div>
  )
}
