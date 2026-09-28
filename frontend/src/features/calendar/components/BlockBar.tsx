import { Wrench } from 'lucide-react'
import { memo } from 'react'
import { cn } from '@/lib/utils'
import { barMetrics, type BlockItem, type RowKind } from '../lib/layout'

/**
 * A room (or bed) taken out of sale: hatched stone, same half-day geometry as stays. On the beds of a dorm
 * a whole-room block is drawn again, lighter and without text (`inherited`).
 */
export const BlockBar = memo(function BlockBar({
  item,
  rowKind,
  dayWidth,
  label,
  text,
}: {
  item: BlockItem
  rowKind: RowKind
  dayWidth: number
  /** Full description (accessible name and tooltip). */
  label: string
  /** What fits inside the bar: the reason, or the kind of block. */
  text: string
}) {
  const { span, lane, inherited } = item
  const { top, height } = barMetrics(rowKind, lane)
  const left = span.start * dayWidth + 1
  const width = Math.max(8, (span.end - span.start) * dayWidth - 2)
  return (
    <div
      data-block
      role="img"
      aria-label={label}
      title={label}
      className={cn(
        'hatch absolute flex items-center gap-1 overflow-hidden rounded-[6px] border border-stone/30 bg-stone-soft px-1.5 text-2xs font-semibold text-stone-ink',
        span.clippedStart && 'rounded-l-none border-l-0',
        span.clippedEnd && 'rounded-r-none border-r-0',
        inherited && 'opacity-60',
      )}
      style={{ left, top, width, height }}
    >
      {!inherited && width >= 28 && <Wrench aria-hidden className="size-3 shrink-0" />}
      {!inherited && width >= 72 && <span className="truncate">{text}</span>}
    </div>
  )
})
