import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { pick, signedPercent } from '../lib/format'
import type { HeatmapModel } from '../lib/heatmap'
import { percent, shortDate, statusText } from '../lib/labels'
import { STEP_CLASS, stepOf } from '../lib/scale'

export interface RecommendationListProps {
  model: HeatmapModel
  currency: string
  selected: ReadonlySet<string>
  activeId: string | null
  canSelect: boolean
  onToggle: (ids: string[]) => void
  onActivate: (id: string) => void
}

/** The table twin of the heatmap (same nights, same selection): every value readable without color. */
export function RecommendationList({ model, currency, selected, activeId, canSelect, onToggle, onActivate }: RecommendationListProps) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const items = model.columns.flatMap((column, c) =>
    model.rows.flatMap((row) => {
      const cell = row.cells[c]?.cell
      return cell ? [{ column, row, cell }] : []
    }),
  )
  if (items.length === 0) {
    return <p className="rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-muted">{t('list.empty')}</p>
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <Table aria-label={t('list.label')} className="num">
        <TableHeader>
          <TableRow>
            {canSelect && (
              <TableHead className="w-10">
                <span className="sr-only">{t('list.selection')}</span>
              </TableHead>
            )}
            <TableHead>{t('list.night')}</TableHead>
            <TableHead>{t('list.category')}</TableHead>
            <TableHead className="text-right">{t('list.current')}</TableHead>
            <TableHead className="text-right">{t('list.recommended')}</TableHead>
            <TableHead className="text-right">{t('list.change')}</TableHead>
            <TableHead className="text-right">{t('list.occupancy')}</TableHead>
            <TableHead>{t('list.status')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map(({ column, row, cell }) => {
            const name = pick(row.roomType.name, lang)
            const date = shortDate(column.date, lang)
            const selectable = canSelect && cell.status === 'pending'
            return (
              <TableRow
                key={cell.id}
                onClick={() => onActivate(cell.id)}
                data-state={selected.has(cell.id) ? 'selected' : undefined}
                className={cn('cursor-pointer', cell.id === activeId && 'bg-accent-soft/40')}
              >
                {canSelect && (
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <Checkbox
                      aria-label={t('list.select', { roomType: name, date })}
                      checked={selected.has(cell.id)}
                      disabled={!selectable}
                      onCheckedChange={() => onToggle([cell.id])}
                    />
                  </TableCell>
                )}
                <TableCell className="whitespace-nowrap first-letter:uppercase">{date}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <span aria-hidden className="h-4 w-1 rounded-full" style={{ background: row.roomType.color }} />
                    <span className="font-semibold text-fg">{name}</span>
                    {model.manyPlans && <span className="text-muted">· {row.ratePlan.code}</span>}
                  </span>
                </TableCell>
                <TableCell className="text-right text-muted">{formatMoney(cell.current_price, currency)}</TableCell>
                <TableCell className="text-right font-semibold text-fg">{formatMoney(cell.recommended_price, currency)}</TableCell>
                <TableCell className="text-right">
                  <span className={cn('rounded-md px-1.5 py-0.5 text-xs font-bold', STEP_CLASS[stepOf(cell.change_percent)])}>
                    {signedPercent(cell.change_percent, lang)}
                  </span>
                </TableCell>
                <TableCell className="text-right text-muted">{cell.occupancy === null ? '—' : percent(cell.occupancy, lang)}</TableCell>
                <TableCell className="text-muted first-letter:uppercase">{statusText(t, cell.status)}</TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
