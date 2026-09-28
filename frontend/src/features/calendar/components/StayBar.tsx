import { useDraggable } from '@dnd-kit/core'
import { ArrowUpRight, ChevronLeft, ChevronRight, CircleDollarSign, Globe, Star } from 'lucide-react'
import { memo, type CSSProperties, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import type { CalStay } from '../api'
import { STATUS_COLORS } from '../lib/constants'
import type { DragMode } from '../lib/dnd'
import { barMetrics, type RowKind, type StayItem } from '../lib/layout'

/** What a drag carries, read back in the grid's drag handlers. */
export interface BarDragData {
  stayId: string
  rowIndex: number
  lane: number
  mode: DragMode
}

const ONLINE_SOURCES = new Set(['ota', 'marketplace', 'booking_engine'])

export interface StayBarProps {
  item: StayItem
  rowKind: RowKind
  rowIndex: number
  dayWidth: number
  /** Accessible name of the bar (guest, code, status, dates, place, flags, channel). */
  label: string
  /** "3 n." shown when the bar is wide enough. */
  nightsText: string
  /** `aria-roledescription` of a movable bar. */
  roleDescription: string
  /** The stay can be dragged to another room or other dates (and stretched when `resizable`). */
  draggable: boolean
  resizable: boolean
  /** Search: `match` rings the bar, `dim` fades the others. */
  emphasis: 'none' | 'match' | 'dim'
  /** Picked up with the keyboard (M): the ghost shows where it goes. */
  lifted: boolean
  describedBy: string
  onOpen: (stay: CalStay) => void
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>, item: StayItem, rowIndex: number) => void
  onBlur: (item: StayItem) => void
}

/**
 * A booking on the grid: from the middle of the arrival day to the middle of the departure day, filled with
 * the color of its state. Click (or Enter) opens it; drag it to another row or days; stretch its right edge
 * to change the departure; M picks it up for the arrow keys.
 */
export const StayBar = memo(function StayBar({
  item,
  rowKind,
  rowIndex,
  dayWidth,
  label,
  nightsText,
  roleDescription,
  draggable,
  resizable,
  emphasis,
  lifted,
  describedBy,
  onOpen,
  onKeyDown,
  onBlur,
}: StayBarProps) {
  const { stay, span, lane, upgrade } = item
  const move = useDraggable({
    id: `move:${stay.id}`,
    data: { stayId: stay.id, rowIndex, lane, mode: 'move' } satisfies BarDragData,
    disabled: !draggable,
  })
  const stretch = useDraggable({
    id: `resize:${stay.id}`,
    data: { stayId: stay.id, rowIndex, lane, mode: 'resize' } satisfies BarDragData,
    disabled: !resizable,
  })

  const { top, height } = barMetrics(rowKind, lane)
  const left = span.start * dayWidth + 1
  const width = Math.max(8, (span.end - span.start) * dayWidth - 2)
  const colors = STATUS_COLORS[stay.status] ?? STATUS_COLORS.confirmed
  const roomy = width >= 96
  const moving = move.isDragging || stretch.isDragging || lifted

  const style: CSSProperties = {
    background: colors.fill,
    color: colors.ink,
    boxShadow: span.clippedStart ? undefined : `inset 3px 0 0 ${colors.edge}`,
    borderColor: colors.edge,
  }

  return (
    <div
      data-bar
      className={cn(
        'group/bar absolute',
        emphasis === 'match' && 'z-[3]',
        emphasis === 'dim' && 'opacity-35',
        moving && 'opacity-45',
      )}
      style={{ left, top, width, height }}
    >
      <button
        ref={move.setNodeRef}
        type="button"
        data-stay-id={stay.id}
        aria-label={label}
        aria-roledescription={draggable ? roleDescription : undefined}
        aria-describedby={draggable ? describedBy : undefined}
        aria-pressed={lifted || undefined}
        {...(draggable ? move.listeners : {})}
        onClick={() => onOpen(stay)}
        onKeyDown={(event) => onKeyDown(event, item, rowIndex)}
        onBlur={() => onBlur(item)}
        className={cn(
          'absolute inset-0 flex items-center gap-1 overflow-hidden rounded-[6px] pr-1.5 text-left text-[12px] leading-4 font-semibold',
          'transition-[box-shadow,transform] duration-150 outline-none',
          'hover:brightness-[0.98] focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-1 focus-visible:ring-offset-surface',
          span.clippedStart ? 'rounded-l-none pl-1' : 'pl-2',
          span.clippedEnd && 'rounded-r-none',
          stay.status === 'tentative' && 'border border-dashed',
          stay.status === 'checked_out' && 'font-medium',
          draggable && 'cursor-grab active:cursor-grabbing',
          emphasis === 'match' && 'ring-2 ring-accent',
          lifted && 'ring-2 ring-accent ring-offset-1 ring-offset-surface',
        )}
        style={style}
      >
        {span.clippedStart && <ChevronLeft aria-hidden className="size-3 shrink-0 opacity-70" />}
        {stay.is_vip && <Star aria-hidden className="size-3 shrink-0 fill-current" />}
        <span className="min-w-0 flex-1 truncate">{stay.guest_name}</span>
        {roomy && <span className="num shrink-0 text-2xs font-semibold opacity-80">{nightsText}</span>}
        {stay.balance_due && <CircleDollarSign aria-hidden className="size-3 shrink-0" />}
        {roomy && upgrade && <ArrowUpRight aria-hidden className="size-3 shrink-0" />}
        {roomy && ONLINE_SOURCES.has(stay.source) && <Globe aria-hidden className="size-3 shrink-0 opacity-70" />}
        {span.clippedEnd && <ChevronRight aria-hidden className="size-3 shrink-0 opacity-70" />}
      </button>
      {resizable && !span.clippedEnd && (
        <div
          ref={stretch.setNodeRef}
          aria-hidden
          {...stretch.listeners}
          className="absolute inset-y-0 -right-1 z-[2] w-3 cursor-ew-resize touch-none rounded-r-[6px] opacity-0 transition-opacity group-hover/bar:opacity-100"
        >
          <span className="absolute inset-y-1.5 right-1.5 w-[3px] rounded-full bg-current opacity-50" style={{ color: colors.edge }} />
        </div>
      )}
    </div>
  )
})
