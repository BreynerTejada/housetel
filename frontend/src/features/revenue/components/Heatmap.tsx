import { Check, ListChecks, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CalendarCell } from '../api'
import { pick, signedPercent } from '../lib/format'
import { columnPendingIds, rowPendingIds, type HeatmapModel } from '../lib/heatmap'
import { changePhrase, shortDate, statusText } from '../lib/labels'
import { STEP_CLASS, STEP_RING, stepOf } from '../lib/scale'

export interface HeatmapProps {
  model: HeatmapModel
  currency: string
  selected: ReadonlySet<string>
  /** Recommendation shown in the detail panel. */
  activeId: string | null
  /** `revenue.manage`: pending cells can be selected for a mass decision. */
  canSelect: boolean
  onToggle: (ids: string[]) => void
  onActivate: (id: string) => void
}

interface Position {
  r: number
  c: number
}

const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max)

/**
 * The price-pressure map: categories × nights, each night colored by the change its recommendation proposes
 * (diverging scale of `lib/scale`) and printing it. A roving focus moves with the arrow keys (Home/End go to
 * the ends of the row) and the detail follows it; a click, Space or Enter selects a pending night (and shows it).
 * Row and night headers select their pending nights at once.
 */
export function Heatmap({ model, currency, selected, activeId, canSelect, onToggle, onActivate }: HeatmapProps) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const rows = model.rows.length
  const cols = model.columns.length
  const [focus, setFocus] = useState<Position>({ r: 0, c: 0 })
  const cells = useRef(new Map<string, HTMLTableCellElement>())
  const pendingFocus = useRef<string | null>(null)
  const current = { r: clamp(focus.r, rows - 1), c: clamp(focus.c, cols - 1) }
  const dateLabels = useMemo(() => model.columns.map((column) => shortDate(column.date, lang)), [model.columns, lang])

  // Keeps DOM focus on the cell after a re-render (e.g. the selection changed).
  useEffect(() => {
    const key = pendingFocus.current
    if (!key) return
    pendingFocus.current = null
    cells.current.get(key)?.focus()
  })

  function cellAt({ r, c }: Position): CalendarCell | null {
    return model.rows[r]?.cells[c]?.cell ?? null
  }

  function moveTo(position: Position) {
    setFocus(position)
    pendingFocus.current = `${position.r}:${position.c}`
    cells.current.get(pendingFocus.current)?.focus()
    const cell = cellAt(position)
    if (cell) onActivate(cell.id)
  }

  function choose(position: Position) {
    setFocus(position)
    const cell = cellAt(position)
    if (!cell) return
    onActivate(cell.id)
    if (canSelect && cell.status === 'pending') onToggle([cell.id])
  }

  function onKeyDown(event: KeyboardEvent<HTMLTableCellElement>, position: Position) {
    const { r, c } = position
    const moves: Record<string, Position> = {
      ArrowUp: { r: r - 1, c },
      ArrowDown: { r: r + 1, c },
      ArrowLeft: { r, c: c - 1 },
      ArrowRight: { r, c: c + 1 },
      Home: { r, c: 0 },
      End: { r, c: cols - 1 },
    }
    const move = moves[event.key]
    if (move) {
      event.preventDefault()
      moveTo({ r: clamp(move.r, rows - 1), c: clamp(move.c, cols - 1) })
    } else if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault()
      choose(position)
    }
  }

  return (
    <div className="relative max-h-[calc(100dvh-14rem)] min-h-40 overflow-auto rounded-lg border border-border bg-surface shadow-xs">
      <table
        role="grid"
        aria-label={t('map.label')}
        aria-multiselectable={canSelect || undefined}
        aria-rowcount={rows + 1}
        aria-colcount={cols + 1}
        className="num w-max min-w-full border-separate border-spacing-[2px] text-[12px]"
      >
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 left-0 z-30 w-24 min-w-24 bg-surface px-2 pb-1.5 text-left align-bottom sm:w-40 sm:min-w-40"
            >
              <span className="eyebrow">{t('map.category')}</span>
            </th>
            {model.columns.map((column, c) => {
              const pendingIds = canSelect ? columnPendingIds(model, column.date) : []
              const label = (
                <>
                  <span className="flex items-center justify-center gap-0.5">
                    {column.holiday && <span aria-hidden className="size-1.5 rounded-full bg-accent" />}
                    <span className={cn('text-2xs font-bold uppercase', column.holiday || column.today ? 'text-accent-ink' : 'text-muted')}>
                      {formatDate(column.date, 'EEEEEE', lang)}
                    </span>
                  </span>
                  <span className={cn('block text-[15px] leading-5 font-bold tracking-[-0.02em]', column.today ? 'text-accent-ink' : 'text-fg')}>
                    {formatDate(column.date, 'd', lang)}
                  </span>
                </>
              )
              return (
                <th
                  key={column.date}
                  scope="col"
                  aria-label={column.holiday ? `${dateLabels[c]} · ${column.holiday}` : dateLabels[c]}
                  title={column.holiday ?? undefined}
                  className={cn(
                    'sticky top-0 z-20 h-14 w-10 min-w-10 bg-surface px-0 pb-1 text-center align-bottom font-normal',
                    column.weekend && 'bg-surface-2',
                    column.today && 'shadow-[inset_0_3px_0_var(--accent)]',
                    column.monthStart && c > 0 && 'shadow-[inset_2px_0_0_var(--border-strong)]',
                  )}
                >
                  {column.monthStart && (
                    <span className="absolute top-1 left-1 text-2xs font-bold whitespace-nowrap text-muted uppercase">
                      {formatDate(column.date, 'MMM', lang)}
                    </span>
                  )}
                  {pendingIds.length > 0 ? (
                    <button
                      type="button"
                      aria-label={t('map.selectNight', { date: dateLabels[c] })}
                      onClick={() => onToggle(pendingIds)}
                      className="w-full rounded-md py-0.5 transition-colors hover:bg-surface-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      {label}
                    </button>
                  ) : (
                    <span className="block py-0.5">{label}</span>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {model.rows.map((row, r) => {
            const name = pick(row.roomType.name, lang)
            const rowIds = canSelect ? rowPendingIds(row) : []
            return (
              <tr key={row.key}>
                <th scope="row" className="sticky left-0 z-10 bg-surface px-1.5 text-left align-middle sm:px-2">
                  <span className="flex w-[5.5rem] items-center gap-2 sm:w-[9.25rem]">
                    <span aria-hidden className="h-7 w-1 shrink-0 rounded-full" style={{ background: row.roomType.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-bold text-fg">{name}</span>
                      <span className="block truncate text-2xs font-semibold tracking-wide text-muted">
                        {row.roomType.code}
                        {model.manyPlans && ` · ${row.ratePlan.code}`}
                      </span>
                    </span>
                    {rowIds.length > 0 && (
                      <button
                        type="button"
                        onClick={() => onToggle(rowIds)}
                        aria-label={t('map.selectRow', { roomType: name })}
                        className="grid size-7 shrink-0 place-items-center rounded-md text-subtle transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                      >
                        <ListChecks aria-hidden className="size-3.5" />
                      </button>
                    )}
                  </span>
                </th>
                {row.cells.map((item, c) => {
                  const cell = item.cell
                  const isCurrent = current.r === r && current.c === c
                  const position = { r, c }
                  const label = cell
                    ? t('map.cellLabel', {
                        roomType: name,
                        date: dateLabels[c],
                        change: changePhrase(t, cell, lang, currency),
                        status: statusText(t, cell.status),
                      })
                    : t('map.noChange', { roomType: name, date: dateLabels[c] })
                  const selectable = canSelect && cell?.status === 'pending'
                  return (
                    <td
                      key={item.date}
                      ref={(element) => {
                        const key = `${r}:${c}`
                        if (element) cells.current.set(key, element)
                        else cells.current.delete(key)
                      }}
                      role="gridcell"
                      tabIndex={isCurrent ? 0 : -1}
                      aria-label={label}
                      title={label}
                      aria-selected={selectable ? selected.has(cell.id) : undefined}
                      data-step={cell ? stepOf(cell.change_percent) : undefined}
                      data-status={cell?.status}
                      onClick={() => choose(position)}
                      onFocus={() => setFocus(position)}
                      onKeyDown={(event) => onKeyDown(event, position)}
                      className={cn(
                        'relative h-10 w-10 min-w-10 rounded-[5px] text-center align-middle font-bold outline-none select-none',
                        'focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                        cell ? 'cursor-pointer' : 'cursor-default',
                        cellClass(cell),
                        selectable && selected.has(cell.id) && 'shadow-[inset_0_0_0_2px_var(--text),inset_0_0_0_4px_var(--surface)]',
                        cell && cell.id === activeId && 'ring-2 ring-accent ring-offset-1 ring-offset-surface',
                      )}
                    >
                      {cell && <CellValue cell={cell} lang={lang} />}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function cellClass(cell: CalendarCell | null): string {
  if (!cell) return STEP_CLASS[0]
  const step = stepOf(cell.change_percent)
  switch (cell.status) {
    case 'pending':
      return STEP_CLASS[step]
    case 'applied':
    case 'auto_applied':
      return cn('bg-surface text-muted', STEP_RING[step])
    case 'approved':
      return 'bg-surface text-warning-ink shadow-[inset_0_0_0_2px_var(--warning)]'
    default:
      return 'bg-surface text-subtle shadow-[inset_0_0_0_1px_var(--border)]'
  }
}

function CellValue({ cell, lang }: { cell: CalendarCell; lang: 'es' | 'en' }) {
  const value = signedPercent(cell.change_percent, lang, { unit: false })
  if (cell.status === 'applied' || cell.status === 'auto_applied') {
    return (
      <>
        <span>{value}</span>
        <Check aria-hidden className="absolute top-0.5 right-0.5 size-2.5 text-success-ink" />
      </>
    )
  }
  if (cell.status === 'approved') {
    return (
      <>
        <span>{value}</span>
        <TriangleAlert aria-hidden className="absolute top-0.5 right-0.5 size-2.5" />
      </>
    )
  }
  if (cell.status === 'rejected') return <span className="line-through decoration-1">{value}</span>
  return <span>{value}</span>
}
