import type { TFunction } from 'i18next'
import { BedSingle, ChevronDown, ChevronRight } from 'lucide-react'
import { memo, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { formatMoney, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CalStay, I18nText } from '../api'
import { blockKindLabel, blockLabel, compactPrice, nightsOf, pick, stayLabel, type RoomIndex } from '../lib/labels'
import type { CalendarRow, StayItem } from '../lib/layout'
import { BlockBar } from './BlockBar'
import { StayBar } from './StayBar'

/** Nightly price of the calendar's plan: `byRoomType → date → {price, stop_sell}`. */
export interface PriceIndex {
  planName: I18nText
  currency: string
  byRoomType: Map<string, Map<string, { price: string | null; stop_sell: boolean }>>
}

export interface RowHandlers {
  onToggle: (key: string) => void
  onOpen: (stay: CalStay) => void
  onBarKeyDown: (event: KeyboardEvent<HTMLButtonElement>, item: StayItem, rowIndex: number) => void
  onBarBlur: (item: StayItem) => void
  onContentPointerDown: (event: ReactPointerEvent<HTMLDivElement>, rowIndex: number) => void
}

export interface GridRowProps {
  row: CalendarRow
  rowIndex: number
  top: number
  labelWidth: number
  dayWidth: number
  dates: readonly string[]
  lang: Lang
  index: RoomIndex
  availability: Record<string, number> | undefined
  prices: PriceIndex | null
  canManage: boolean
  businessDate: string
  /** Stay ids matching the search (`null`: no search). */
  matches: ReadonlySet<string> | null
  liftedStayId: string | null
  describedBy: string
  handlers: RowHandlers
}

/** What the parts of a row share: one `t` per row (cells and bars take their words from it, so scrolling never mounts hundreds of i18n hooks). */
type PartProps = GridRowProps & { t: TFunction }

const ROOM_INK: Record<string, string> = {
  clean: 'text-success-ink',
  dirty: 'text-warning-ink',
  inspected: 'text-info-ink',
  out_of_service: 'text-stone-ink',
}

export const GridRow = memo(function GridRow(props: GridRowProps) {
  const { row, rowIndex, top, labelWidth, dayWidth, dates } = props
  const { t } = useTranslation('calendar')
  const name = pick(props.row.roomType.name, props.lang)
  const width = labelWidth + dates.length * dayWidth

  let label: string
  switch (row.kind) {
    case 'category':
      label = t('grid.rowCategory', { name, code: row.roomType.code })
      break
    case 'unassigned': {
      const lane = Number(row.key.split(':')[2] ?? 0)
      label = lane === 0 ? t('grid.rowUnassigned', { name }) : t('grid.rowUnassignedLane', { name, lane: lane + 1 })
      break
    }
    case 'room':
      label = t('grid.rowRoom', { number: row.room?.number })
      break
    case 'dorm':
      label = t('grid.rowDorm', { number: row.room?.number })
      break
    case 'bed':
      label = t('grid.rowBed', { label: row.bed?.label, room: row.room?.number })
      break
  }

  return (
    <div
      role="row"
      aria-rowindex={rowIndex + 2}
      aria-label={label}
      data-row-key={row.key}
      className={cn(
        'absolute top-0 left-0 flex border-b border-border/70',
        row.kind === 'category' && 'border-border bg-surface-2/55',
        row.kind === 'unassigned' && 'border-dashed',
        row.kind === 'bed' && 'border-border/40',
      )}
      style={{ transform: `translateY(${top}px)`, width, height: row.height }}
    >
      <RowHeader {...props} t={t} name={name} />
      <RowContent {...props} t={t} />
    </div>
  )
})

function RowHeader({ row, labelWidth, handlers, name, t }: PartProps & { name: string }) {
  const base = 'sticky left-0 z-10 flex h-full shrink-0 items-center gap-2 border-r border-border px-2 sm:px-3'
  const style = { width: labelWidth }

  if (row.kind === 'category') {
    const units = row.roomType.kind === 'dorm' ? row.roomType.rooms.reduce((sum, room) => sum + room.beds.length, 0) : row.roomType.rooms.length
    const folded = Boolean(row.collapsed)
    return (
      <div role="rowheader" className={cn(base, 'bg-surface-2')} style={style}>
        <span aria-hidden className="h-7 w-1 shrink-0 rounded-full" style={{ background: row.roomType.color }} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] leading-5 font-bold text-fg">{name}</span>
          <span className="block truncate text-2xs font-semibold tracking-wide text-muted">
            {row.roomType.code}
            <span className="hidden sm:inline">
              {' · '}
              {t(row.roomType.kind === 'dorm' ? 'grid.beds' : 'grid.rooms', { count: units })}
            </span>
          </span>
        </span>
        <button
          type="button"
          aria-label={t(folded ? 'grid.expand' : 'grid.collapse', { name })}
          aria-expanded={!folded}
          onClick={() => handlers.onToggle(`rt:${row.roomType.id}`)}
          className="grid size-7 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-surface-3 hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none"
        >
          {folded ? <ChevronRight aria-hidden className="size-4" /> : <ChevronDown aria-hidden className="size-4" />}
        </button>
      </div>
    )
  }

  if (row.kind === 'unassigned') {
    const count = row.unassignedCount ?? 0
    const folded = Boolean(row.collapsed)
    return (
      <div role="rowheader" className={cn(base, 'bg-surface')} style={style}>
        {row.first && (
          <>
            <span className="eyebrow min-w-0 truncate !text-subtle">{t('grid.unassigned')}</span>
            {count > 0 && (
              <span aria-hidden className="num shrink-0 rounded-full bg-warning-soft px-1.5 text-2xs leading-4 font-bold text-warning-ink">
                {count}
              </span>
            )}
            {count > 0 && (
              <button
                type="button"
                aria-label={t(folded ? 'grid.expandUnassigned' : 'grid.collapseUnassigned', { name })}
                aria-expanded={!folded}
                onClick={() => handlers.onToggle(`un:${row.roomType.id}`)}
                className="ml-auto grid size-6 shrink-0 place-items-center rounded-md text-subtle transition-colors hover:bg-surface-2 hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none"
              >
                {folded ? <ChevronRight aria-hidden className="size-3.5" /> : <ChevronDown aria-hidden className="size-3.5" />}
              </button>
            )}
          </>
        )}
      </div>
    )
  }

  if (row.kind === 'bed') {
    return (
      <div role="rowheader" className={cn(base, 'bg-surface pl-4 sm:pl-8')} style={style}>
        <BedSingle aria-hidden className="size-3.5 shrink-0 text-subtle" />
        <span className="num truncate text-xs font-semibold text-muted">{row.bed?.label}</span>
      </div>
    )
  }

  const room = row.room
  const status = room?.housekeeping_status ?? 'clean'
  return (
    <div role="rowheader" className={cn(base, 'bg-surface')} style={style}>
      <RoomKeyTag number={room?.number ?? ''} status={status} size="sm" />
      <span className="hidden min-w-0 sm:block">
        {row.kind === 'dorm' ? (
          <span className="block truncate text-2xs font-semibold text-muted">{t('grid.beds', { count: room?.beds.length ?? 0 })}</span>
        ) : (
          <>
            <span className={cn('block truncate text-2xs leading-4 font-semibold', ROOM_INK[status] ?? 'text-muted')}>
              {t(`status.room.${status}`, { ns: 'common', defaultValue: status })}
            </span>
            {room?.floor && <span className="block truncate text-2xs leading-4 text-subtle">{t('grid.floor', { floor: room.floor })}</span>}
          </>
        )}
      </span>
    </div>
  )
}

function RowContent(props: PartProps) {
  const { row, dates, dayWidth, rowIndex, handlers, t } = props
  const width = dates.length * dayWidth

  if (row.kind === 'category') return <CategoryCells {...props} />

  if (row.kind === 'unassigned' && row.collapsed) {
    return (
      <div className="flex" style={{ width }}>
        {dates.map((date, night) => (
          <CountCell key={date} width={dayWidth} count={row.counts?.[night] ?? 0} t={t} />
        ))}
      </div>
    )
  }

  // Empty stretches of a row take the pointer to draw a new booking (the grid ignores presses on bars).
  const bars = <Bars {...props} />
  const drawable = props.canManage
  if (row.kind === 'dorm') {
    const total = row.room?.beds.length ?? 0
    return (
      <div
        data-row-content
        className={cn('relative flex', drawable && 'cursor-cell')}
        style={{ width }}
        onPointerDown={(event) => handlers.onContentPointerDown(event, rowIndex)}
      >
        {dates.map((date, night) => (
          <FreeBedsCell key={date} width={dayWidth} free={row.free?.[night] ?? total} total={total} t={t} />
        ))}
        <div className="pointer-events-none absolute inset-0 [&>*]:pointer-events-auto">{bars}</div>
      </div>
    )
  }

  return (
    <div
      role="cell"
      aria-colspan={dates.length}
      data-row-content
      className={cn('relative', drawable && 'cursor-cell')}
      style={{ width }}
      onPointerDown={(event) => handlers.onContentPointerDown(event, rowIndex)}
    >
      {bars}
    </div>
  )
}

function Bars({ row, rowIndex, dayWidth, lang, index, canManage, businessDate, matches, liftedStayId, describedBy, handlers, t }: PartProps) {
  const roleDescription = t('bar.roleDescription')
  return (
    <>
      {row.items.map((item) => {
        if (item.type === 'block') {
          return (
            <BlockBar
              key={`${item.id}:${item.inherited ? 'i' : 'o'}`}
              item={item}
              rowKind={row.kind}
              dayWidth={dayWidth}
              label={blockLabel(t, lang, item.block)}
              text={item.block.reason || blockKindLabel(t, item.block.kind)}
            />
          )
        }
        const { stay } = item
        const movable = canManage && stay.status !== 'checked_out'
        const emphasis = matches === null || matches.size === 0 ? 'none' : matches.has(stay.id) ? 'match' : 'dim'
        return (
          <StayBar
            key={item.id}
            item={item}
            rowKind={row.kind}
            rowIndex={rowIndex}
            dayWidth={dayWidth}
            label={stayLabel(t, lang, stay, index)}
            nightsText={t('bar.nightsShort', { count: nightsOf(stay) })}
            roleDescription={roleDescription}
            draggable={movable}
            resizable={movable && stay.checkout >= businessDate}
            emphasis={emphasis}
            lifted={liftedStayId === stay.id}
            describedBy={describedBy}
            onOpen={handlers.onOpen}
            onKeyDown={handlers.onBarKeyDown}
            onBlur={handlers.onBarBlur}
          />
        )
      })}
    </>
  )
}

// The cells below are what scrolling mounts most (30 per row): one element per cell plus the visible marks,
// with the words for screen readers in the cell's own `aria-label` instead of extra hidden spans.

function CategoryCells({ row, dates, dayWidth, availability, prices, lang, t }: PartProps) {
  const nightly = prices?.byRoomType.get(row.roomType.id)
  const planName = prices ? pick(prices.planName, lang) : ''
  const showPrice = dayWidth >= 52
  const compact = dayWidth < 56
  return (
    <div className="flex" style={{ width: dates.length * dayWidth }}>
      {dates.map((date) => {
        const units = availability?.[date]
        const rate = nightly?.get(date)
        const spoken = [
          availabilityText(t, units),
          rate?.price ? t('grid.price', { plan: planName, price: formatMoney(rate.price, prices?.currency) }) : null,
          rate?.stop_sell ? t('grid.closed') : null,
        ].filter(Boolean)
        return (
          <div
            key={date}
            role="cell"
            aria-label={spoken.join(' · ') || undefined}
            className="flex h-full shrink-0 flex-col items-center justify-center gap-0.5 px-0.5"
            style={{ width: dayWidth }}
          >
            <AvailabilityMark units={units} compact={compact} t={t} />
            {rate?.price && showPrice && (
              <span
                aria-hidden
                className={cn('num text-2xs leading-3 font-medium text-muted', rate.stop_sell && 'text-subtle line-through decoration-danger/70')}
              >
                {compactPrice(rate.price, lang)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function availabilityText(t: TFunction, units: number | undefined): string | null {
  if (units === undefined) return null
  if (units < 0) return t('grid.overbooked', { count: -units })
  if (units === 0) return t('grid.full')
  return t('grid.free', { count: units })
}

function AvailabilityMark({ units, compact, t }: { units: number | undefined; compact: boolean; t: TFunction }) {
  if (units === undefined) {
    return (
      <span aria-hidden className="text-2xs text-subtle">
        ·
      </span>
    )
  }
  if (units < 0) {
    return (
      <span aria-hidden className="num rounded-full bg-danger-soft px-1.5 text-2xs leading-4 font-bold text-danger-ink">
        −{-units}
      </span>
    )
  }
  if (units === 0) {
    return (
      <span aria-hidden className="rounded-full bg-danger-soft px-1.5 text-2xs leading-4 font-bold text-danger-ink">
        {compact ? '0' : t('grid.full')}
      </span>
    )
  }
  return (
    <span aria-hidden className={cn('num text-[13px] leading-4 font-bold', units <= 2 ? 'text-warning-ink' : 'text-fg')}>
      {units}
    </span>
  )
}

function FreeBedsCell({ width, free, total, t }: { width: number; free: number; total: number; t: TFunction }) {
  return (
    <div role="cell" aria-label={t('grid.freeBeds', { free, total })} className="flex h-full shrink-0 items-end justify-end px-1.5 pb-0.5" style={{ width }}>
      <span aria-hidden className={cn('num text-2xs font-semibold', free === 0 ? 'text-danger-ink' : 'text-subtle')}>
        {free}/{total}
      </span>
    </div>
  )
}

function CountCell({ width, count, t }: { width: number; count: number; t: TFunction }) {
  return (
    <div
      role="cell"
      aria-label={count > 0 ? t('grid.unassignedCount', { count }) : undefined}
      className="flex h-full shrink-0 items-center justify-center"
      style={{ width }}
    >
      {count > 0 && (
        <span aria-hidden className="num rounded-full bg-warning-soft px-1.5 text-2xs leading-4 font-bold text-warning-ink">
          {count}
        </span>
      )}
    </div>
  )
}
