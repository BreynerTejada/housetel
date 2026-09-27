import { cn } from '@/lib/utils'
import type { HousekeepingStatus } from '../api'

const TINT: Record<string, string> = {
  clean: 'bg-room-clean-soft text-success-ink',
  dirty: 'bg-room-dirty-soft text-warning-ink',
  inspected: 'bg-room-inspected-soft text-info-ink',
  out_of_service: 'bg-room-ooo-soft text-stone-ink hatch',
  occupied: 'bg-room-occupied-soft text-accent-ink',
}

/**
 * A room number drawn as a key tag from the front-desk rack (the login page motif), tinted by its
 * housekeeping state. `inactive` rooms are hatched stone. Exported for other features.
 */
export function RoomKeyTag({
  number,
  status = 'clean',
  inactive = false,
  size = 'md',
  className,
}: {
  number: string
  status?: HousekeepingStatus | 'occupied' | string
  inactive?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  return (
    <span
      data-status={inactive ? 'inactive' : status}
      className={cn(
        'relative inline-flex shrink-0 items-end justify-end rounded-md font-bold leading-none num',
        size === 'sm' && 'h-7 min-w-10 px-1.5 pb-1 text-[11px]',
        size === 'md' && 'h-9 min-w-12 px-2 pb-1.5 text-xs',
        size === 'lg' && 'h-14 min-w-18 px-3 pb-2 text-lg',
        inactive ? 'bg-stone-soft text-stone-ink hatch' : (TINT[status] ?? TINT.clean),
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          'absolute rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]',
          size === 'lg' ? 'top-2 left-2 size-2' : 'top-1.5 left-1.5 size-1.5',
        )}
      />
      {number}
    </span>
  )
}

export default RoomKeyTag
