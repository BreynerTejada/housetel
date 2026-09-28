import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { pickupTone } from '../../lib/groups'

const FILL = { success: 'bg-success', info: 'bg-info', warning: 'bg-warning', neutral: 'bg-stone' } as const

/**
 * Allotment pickup at a glance: rooms taken of the rooms held and the room-night percentage, as a bar that
 * fills in the tone of how far the group got (sand → slate → sage).
 */
export function PickupMeter({
  picked,
  total,
  pct,
  rooms,
  units,
  compact = false,
}: {
  /** Room nights picked up (capped at the block's units per night). */
  picked: number
  /** Room nights held by the blocks. */
  total: number
  pct: number | null
  /** Rooms (stays) picked up and units held (per night). */
  rooms: number
  units: number
  compact?: boolean
}) {
  const { t } = useTranslation('frontdesk')
  const tone = pickupTone(pct)
  const ratio = total > 0 ? Math.min(1, picked / total) : 0
  const label = t('groups.pickupLabel', { rooms, units, pct: Math.round(pct ?? 0) })
  return (
    <span className={cn('grid gap-1', compact ? 'text-xs' : 'text-[13px]')}>
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-muted">{t('groups.pickup')}</span>
        <span className="num font-semibold text-fg">{Math.round(pct ?? 0)} %</span>
      </span>
      <span
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={picked}
        className="block h-1.5 overflow-hidden rounded-full bg-surface-3"
      >
        <span className={cn('block h-full rounded-full', FILL[tone as keyof typeof FILL] ?? 'bg-accent')} style={{ width: `${ratio * 100}%` }} />
      </span>
      <span className="num text-muted">{t('groups.pickupRooms', { rooms, units })}</span>
    </span>
  )
}
