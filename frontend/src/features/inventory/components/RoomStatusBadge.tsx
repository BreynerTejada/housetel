import { StatusBadge } from '@/components/StatusBadge'
import type { HousekeepingStatus } from '../api'

/**
 * Housekeeping status of a room (clean · dirty · inspected · out of service), in the room-state colors of
 * the design system. Exported for other features (housekeeping, calendar, front desk).
 */
export function RoomStatusBadge({ status, className }: { status: HousekeepingStatus | string; className?: string }) {
  return <StatusBadge kind="room" status={status} className={className} />
}

export default RoomStatusBadge
