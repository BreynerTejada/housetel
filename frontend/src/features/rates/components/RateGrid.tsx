import { Ban, LogIn, LogOut, SlidersHorizontal, type LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { formatDate, formatMoney, formatNumber, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { GridResponse, GridRoomType, GridRow } from '../api'
import { isWeekendNight, moveFocus, parseAmount, parseLos, type CellChange, type Position } from '../lib/grid-utils'
import { pick, SOURCE_INK } from '../lib/text'

type Kind = 'price' | 'min_los' | 'cta' | 'ctd' | 'stop_sell'
type ToggleKind = 'cta' | 'ctd' | 'stop_sell'
type Direction = 'up' | 'down' | 'left' | 'right'

const TOGGLE_ICONS: Record<ToggleKind, LucideIcon> = { cta: LogIn, ctd: LogOut, stop_sell: Ban }
const ROW_LABELS: Record<Kind, string> = {
  price: 'price',
  min_los: 'minLos',
  cta: 'cta',
  ctd: 'ctd',
  stop_sell: 'stopSell',
}

interface Line {
  roomType: GridRoomType
  kind: Kind
}

interface Editing {
  r: number
  c: number
  draft: string
  selectAll: boolean
}

export interface RateGridProps {
  grid: GridResponse
  /** Business date of the property (`YYYY-MM-DD`). */
  today: string
  /** False for derived plans and for users without `rates.manage`: cells stay navigable, never editable. */
  editable: boolean
  showRestrictions: boolean
  /** `${roomTypeId}:${date}:${field}` of the cells being saved. */
  pendingKeys: ReadonlySet<string>
  onChange: (change: CellChange) => void
  onBulkEdit?: (roomTypeId: string) => void
}

const cellKey = (r: number, c: number) => `${r}:${c}`

function step(pos: Position, direction: Direction, rows: number, cols: number): Position {
  const r = direction === 'down' ? pos.r + 1 : direction === 'up' ? pos.r - 1 : pos.r
  const c = direction === 'right' ? pos.c + 1 : direction === 'left' ? pos.c - 1 : pos.c
  return { r: Math.min(Math.max(r, 0), rows - 1), c: Math.min(Math.max(c, 0), cols - 1) }
}

/**
 * The rate grid: categories × nights. A roving focus moves with the arrow keys (Home/End, Ctrl+Home/End);
 * on a price or minimum-stay cell, Enter/F2 or typing a digit edits it; Enter saves and goes down, Tab saves
 * and goes right, Escape discards, Delete clears a minimum stay. Restriction cells are toggles.
 */
export function RateGrid({ grid, today, editable, showRestrictions, pendingKeys, onChange, onBulkEdit }: RateGridProps) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const currency = grid.currency

  const lines = useMemo<Line[]>(() => {
    const kinds: Kind[] = showRestrictions ? ['price', 'min_los', 'cta', 'ctd', 'stop_sell'] : ['price', 'min_los']
    return grid.room_types.flatMap((roomType) => kinds.map((kind) => ({ roomType, kind })))
  }, [grid.room_types, showRestrictions])
  const rows = lines.length
  const cols = grid.dates.length
  const holidays = useMemo(() => new Map(grid.holidays.map((holiday) => [holiday.date, holiday.name])), [grid.holidays])
  const dateLabels = useMemo(() => grid.dates.map((date) => formatDate(date, 'EEE d MMM', lang)), [grid.dates, lang])

  const [focus, setFocus] = useState<Position>({ r: 0, c: 0 })
  const [editing, setEditing] = useState<Editing | null>(null)
  const editingRef = useRef<Editing | null>(null)
  const pendingFocus = useRef<string | null>(null)
  const cells = useRef(new Map<string, HTMLElement>())
  const active = { r: Math.min(focus.r, rows - 1), c: Math.min(focus.c, cols - 1) }

  // Move DOM focus once the target cell is rendered (after an edit the button is mounted again).
  useEffect(() => {
    const key = pendingFocus.current
    if (!key) return
    pendingFocus.current = null
    cells.current.get(key)?.focus()
  })

  function focusCell(pos: Position) {
    setFocus(pos)
    pendingFocus.current = cellKey(pos.r, pos.c)
    cells.current.get(pendingFocus.current)?.focus()
  }

  function startEdit(r: number, c: number, draft: string, selectAll: boolean) {
    const next = { r, c, draft, selectAll }
    editingRef.current = next
    setFocus({ r, c })
    setEditing(next)
  }

  function setDraft(draft: string) {
    if (!editingRef.current) return
    editingRef.current = { ...editingRef.current, draft }
    setEditing(editingRef.current)
  }

  function cancel() {
    const current = editingRef.current
    if (!current) return
    editingRef.current = null
    setEditing(null)
    focusCell({ r: current.r, c: current.c })
  }

  function commit(direction: Direction | null) {
    const current = editingRef.current
    if (!current) return
    editingRef.current = null
    setEditing(null)
    const { roomType, kind } = lines[current.r]
    const row = roomType.rows[current.c]
    if (kind === 'price') {
      const amount = parseAmount(current.draft)
      if (amount === null) {
        if (current.draft.trim()) toast.error(t('grid.invalidPrice'))
      } else if (row.price === null || Number(amount) !== Number(row.price)) {
        onChange({ roomTypeId: roomType.id, date: row.date, field: 'price', value: amount })
      }
    } else {
      const los = parseLos(current.draft)
      if (los === undefined) toast.error(t('grid.invalidMinLos'))
      else if (los !== row.min_los) onChange({ roomTypeId: roomType.id, date: row.date, field: 'min_los', value: los })
    }
    if (direction) focusCell(step(current, direction, rows, cols))
  }

  function onCellKeyDown(event: KeyboardEvent<HTMLElement>, r: number, c: number) {
    const moved = moveFocus({ r, c }, event.key, { rows, cols }, { ctrl: event.ctrlKey || event.metaKey })
    if (moved) {
      event.preventDefault()
      focusCell(moved)
      return
    }
    const { roomType, kind } = lines[r]
    if (!editable || (kind !== 'price' && kind !== 'min_los')) return
    const row = roomType.rows[c]
    if (event.key === 'Enter' || event.key === 'F2') {
      event.preventDefault()
      startEdit(r, c, kind === 'price' ? editableAmount(row.price, lang) : row.min_los ? String(row.min_los) : '', true)
    } else if (/^\d$/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      startEdit(r, c, event.key, false)
    } else if ((event.key === 'Delete' || event.key === 'Backspace') && kind === 'min_los' && row.min_los !== null) {
      event.preventDefault()
      onChange({ roomTypeId: roomType.id, date: row.date, field: 'min_los', value: null })
    }
  }

  function register(r: number, c: number) {
    return (element: HTMLElement | null) => {
      if (element) cells.current.set(cellKey(r, c), element)
      else cells.current.delete(cellKey(r, c))
    }
  }

  const planName = grid.rate_plan ? pick(grid.rate_plan.name, lang) : ''

  return (
    <div className="relative max-h-[calc(100dvh-15rem)] min-h-72 overflow-auto rounded-lg border border-border bg-surface shadow-xs">
      <table
        role="grid"
        aria-label={t('grid.label', { plan: planName })}
        aria-readonly={!editable || undefined}
        aria-rowcount={rows + grid.room_types.length + 1}
        aria-colcount={cols + 1}
        className="num w-max min-w-full border-separate border-spacing-0 text-[13px]"
      >
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 left-0 z-30 w-28 min-w-28 border-r border-b border-border bg-surface px-2 text-left align-bottom sm:w-52 sm:min-w-52 sm:px-3"
            >
              <span className="eyebrow block w-24 pb-2 sm:w-44">{t('grid.nights')}</span>
            </th>
            {grid.dates.map((date, c) => {
              const holiday = holidays.get(date)
              const isToday = date === today
              const showMonth = c === 0 || date.endsWith('-01')
              return (
                <th
                  key={date}
                  scope="col"
                  aria-label={holiday ? `${dateLabels[c]} · ${holiday}` : dateLabels[c]}
                  title={holiday}
                  className={cn(
                    'sticky top-0 z-20 h-14 min-w-[5.5rem] border-b border-border bg-surface px-2 text-right align-bottom font-normal',
                    isWeekendNight(date) && 'bg-surface-2',
                    isToday && 'shadow-[inset_0_3px_0_var(--accent)]',
                  )}
                >
                  <span className="flex items-center justify-end gap-1">
                    {holiday && <span aria-hidden className="size-1.5 rounded-full bg-accent" />}
                    <span className={cn('eyebrow', (holiday || isToday) && 'text-accent-ink')}>
                      {formatDate(date, 'EEE', lang)}
                    </span>
                  </span>
                  <span className="flex items-baseline justify-end gap-1 pb-1.5">
                    {showMonth && <span className="text-2xs font-semibold text-muted uppercase">{formatDate(date, 'MMM', lang)}</span>}
                    <span className={cn('text-[17px] leading-6 font-bold tracking-[-0.02em]', isToday ? 'text-accent-ink' : 'text-fg')}>
                      {formatDate(date, 'd', lang)}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        {grid.room_types.map((roomType) => {
          const name = pick(roomType.name, lang)
          return (
            <tbody key={roomType.id}>
              <tr>
                <th
                  scope="row"
                  className="sticky left-0 z-10 border-t border-r border-border bg-bg px-2 py-2 text-left align-middle sm:px-3"
                >
                  <span className="flex w-24 items-center gap-2 sm:w-44">
                    <span aria-hidden className="h-7 w-1 shrink-0 rounded-full" style={{ background: roomType.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-bold text-fg">{name}</span>
                      <span className="block truncate text-2xs font-semibold tracking-wide text-muted">
                        {roomType.code}
                        <span className="hidden sm:inline"> · {t('grid.rows.available')}</span>
                      </span>
                    </span>
                    {editable && onBulkEdit && (
                      <button
                        type="button"
                        onClick={() => onBulkEdit(roomType.id)}
                        aria-label={t('grid.bulkRoomType', { roomType: name })}
                        className="hidden size-7 shrink-0 place-items-center rounded-md text-subtle transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 sm:grid"
                      >
                        <SlidersHorizontal aria-hidden className="size-3.5" />
                      </button>
                    )}
                  </span>
                </th>
                {roomType.rows.map((row) => (
                  <td
                    key={row.date}
                    className={cn(
                      'border-t border-border bg-bg px-2 text-right align-middle',
                      isWeekendNight(row.date) && 'bg-surface-2/70',
                    )}
                  >
                    <Availability value={row.available} />
                  </td>
                ))}
              </tr>
              {lines.map((line, r) => {
                if (line.roomType !== roomType) return null
                return (
                  <tr key={line.kind}>
                    <th
                      scope="row"
                      className={cn(
                        'sticky left-0 z-10 border-r border-border bg-surface py-0 pr-2 pl-3 text-left text-xs font-medium whitespace-nowrap text-muted sm:pr-3 sm:pl-6',
                        line.kind === 'price' && 'font-semibold text-fg',
                      )}
                    >
                      <span className="sm:hidden">{t(`grid.rowsShort.${ROW_LABELS[line.kind]}`)}</span>
                      <span className="hidden sm:inline">{t(`grid.rows.${ROW_LABELS[line.kind]}`)}</span>
                    </th>
                    {roomType.rows.map((row, c) => {
                      const isActive = active.r === r && active.c === c
                      const pending = pendingKeys.has(`${roomType.id}:${row.date}:${line.kind}`)
                      const tdClass = cn(
                        'relative border-border p-0',
                        isWeekendNight(row.date) && 'bg-surface-2/60',
                        line.kind === 'price' && 'border-t border-border/60',
                      )
                      const common = {
                        ref: register(r, c),
                        tabIndex: isActive ? 0 : -1,
                        onFocus: () => setFocus({ r, c }),
                        onKeyDown: (event: KeyboardEvent<HTMLElement>) => onCellKeyDown(event, r, c),
                      }
                      if (line.kind === 'cta' || line.kind === 'ctd' || line.kind === 'stop_sell') {
                        const kind = line.kind
                        return (
                          <td key={row.date} className={tdClass}>
                            <ToggleCell
                              {...common}
                              kind={kind}
                              on={row[kind]}
                              editable={editable}
                              pending={pending}
                              label={t(`grid.cell.${kind === 'stop_sell' ? 'stopSell' : kind}`, {
                                roomType: name,
                                date: dateLabels[c],
                              })}
                              onToggle={() =>
                                onChange({ roomTypeId: roomType.id, date: row.date, field: kind, value: !row[kind] })
                              }
                            />
                          </td>
                        )
                      }
                      const isEditing = editing !== null && editing.r === r && editing.c === c
                      if (isEditing) {
                        return (
                          <td key={row.date} className={tdClass}>
                            <input
                              autoFocus
                              inputMode="numeric"
                              autoComplete="off"
                              aria-label={t(line.kind === 'price' ? 'grid.cell.editPrice' : 'grid.cell.editMinLos', {
                                roomType: name,
                                date: dateLabels[c],
                              })}
                              value={editing.draft}
                              onChange={(event) => setDraft(event.target.value)}
                              onFocus={(event) => {
                                const input = event.currentTarget
                                if (editing.selectAll) input.select()
                                else input.setSelectionRange(input.value.length, input.value.length)
                              }}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter') {
                                  event.preventDefault()
                                  commit(event.shiftKey ? 'up' : 'down')
                                } else if (event.key === 'Tab') {
                                  event.preventDefault()
                                  commit(event.shiftKey ? 'left' : 'right')
                                } else if (event.key === 'Escape') {
                                  event.preventDefault()
                                  cancel()
                                }
                              }}
                              onBlur={() => commit(null)}
                              className={cn(
                                'block w-full rounded-none border-2 border-accent bg-surface px-2 text-right font-semibold text-fg outline-none',
                                line.kind === 'price' ? 'h-10' : 'h-8',
                              )}
                            />
                          </td>
                        )
                      }
                      return (
                        <td key={row.date} className={tdClass}>
                          {line.kind === 'price' ? (
                            <PriceCell
                              {...common}
                              row={row}
                              currency={currency}
                              lang={lang}
                              pending={pending}
                              showMarkers={!showRestrictions}
                              label={t('grid.cell.price', {
                                roomType: name,
                                date: dateLabels[c],
                                value: row.price === null ? t('grid.noPrice') : formatMoney(row.price, currency),
                              })}
                              onDoubleClick={() => editable && startEdit(r, c, editableAmount(row.price, lang), true)}
                            />
                          ) : (
                            <LosCell
                              {...common}
                              value={row.min_los}
                              pending={pending}
                              label={t('grid.cell.minLos', {
                                roomType: name,
                                date: dateLabels[c],
                                value: row.min_los ? t('grid.nightsCount', { count: row.min_los }) : t('grid.noMinLos'),
                              })}
                              onDoubleClick={() => editable && startEdit(r, c, row.min_los ? String(row.min_los) : '', true)}
                            />
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          )
        })}
      </table>
    </div>
  )
}

function editableAmount(price: string | null, lang: Lang): string {
  return price === null ? '' : formatNumber(Number(price), lang, 0)
}

const cellButton =
  'relative block w-full px-2 text-right outline-none transition-colors focus-visible:z-[5] focus-visible:bg-accent-soft/50 focus-visible:shadow-[inset_0_0_0_2px_var(--accent)]'

interface CellProps {
  ref: (element: HTMLElement | null) => void
  tabIndex: number
  onFocus: () => void
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void
  label: string
  pending: boolean
}

function PriceCell({
  row,
  currency,
  lang,
  showMarkers,
  label,
  pending,
  onDoubleClick,
  ...props
}: CellProps & { row: GridRow; currency: string; lang: Lang; showMarkers: boolean; onDoubleClick: () => void }) {
  const ink = SOURCE_INK[row.source]
  const markers = showMarkers ? (['cta', 'ctd', 'stop_sell'] as const).filter((kind) => row[kind]) : []
  return (
    <button
      type="button"
      aria-label={label}
      data-source={row.source}
      onDoubleClick={onDoubleClick}
      className={cn(cellButton, 'h-10 font-semibold text-fg hover:bg-surface-2/80', pending && 'animate-pulse')}
      {...props}
    >
      {row.price === null ? (
        <span className="text-warning-ink">—</span>
      ) : (
        <span className={cn(row.stop_sell && 'text-muted line-through decoration-danger/70')}>
          {formatNumber(Number(row.price), lang, currency === 'COP' ? 0 : 2)}
        </span>
      )}
      {markers.length > 0 && (
        <span aria-hidden className="absolute top-1 left-1.5 flex gap-0.5 text-danger-ink">
          {markers.map((kind) => {
            const Icon = TOGGLE_ICONS[kind]
            return <Icon key={kind} className="size-2.5" />
          })}
        </span>
      )}
      {ink && <span aria-hidden className="absolute inset-x-2 bottom-[5px] h-[3px] rounded-full" style={{ background: ink }} />}
    </button>
  )
}

function LosCell({ value, label, pending, onDoubleClick, ...props }: CellProps & { value: number | null; onDoubleClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      onDoubleClick={onDoubleClick}
      className={cn(cellButton, 'h-8 text-[12px] hover:bg-surface-2/80', value ? 'font-semibold text-fg' : 'text-subtle', pending && 'animate-pulse')}
      {...props}
    >
      {value ?? '—'}
    </button>
  )
}

function ToggleCell({
  kind,
  on,
  editable,
  label,
  pending,
  onToggle,
  ...props
}: CellProps & { kind: ToggleKind; on: boolean; editable: boolean; onToggle: () => void }) {
  const Icon = TOGGLE_ICONS[kind]
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={on}
      aria-disabled={!editable || undefined}
      onClick={() => editable && onToggle()}
      className={cn(cellButton, 'group grid h-7 place-items-center', !editable && 'cursor-default', pending && 'animate-pulse')}
      {...props}
    >
      {on ? (
        <span aria-hidden className="grid size-[18px] place-items-center rounded-[5px] border border-danger/35 bg-danger-soft text-danger-ink">
          <Icon className="size-3" />
        </span>
      ) : (
        <span
          aria-hidden
          className={cn(
            'grid size-[18px] place-items-center rounded-[5px] border border-transparent transition-colors',
            editable && 'group-hover:border-border-strong group-focus-visible:border-border-strong',
          )}
        >
          <span className="size-1 rounded-full bg-border-strong group-hover:opacity-0 group-focus-visible:opacity-0" />
        </span>
      )}
    </button>
  )
}

function Availability({ value }: { value: number | null }) {
  const { t } = useTranslation('rates')
  if (value === null) return <span className="text-subtle">—</span>
  if (value <= 0) {
    return (
      <span className="inline-flex rounded-full bg-danger-soft px-1.5 py-px text-2xs font-bold text-danger-ink">
        {value < 0 ? t('grid.overbooked', { count: -value }) : t('grid.full')}
      </span>
    )
  }
  return <span className={cn('text-[12px] font-semibold', value <= 2 ? 'text-warning-ink' : 'text-muted')}>{value}</span>
}
