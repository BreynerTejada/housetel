import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { unitLabel } from '../lib/labels'
import type { UnitOption } from '../lib/units'

const VISIBLE = 6

/** Radio list of rooms (key tag, housekeeping state, "assigned", "still occupied", "other category"). */
export function RoomChoice({
  units,
  value,
  onChange,
  labelId,
  name,
}: {
  units: UnitOption[]
  value: string | null
  onChange: (key: string) => void
  /** Id of the visible heading that names the group. */
  labelId: string
  name?: string
}) {
  const { t } = useTranslation('frontdesk')
  const fallbackName = useId()
  const [showAll, setShowAll] = useState(false)
  const selectedIndex = units.findIndex((unit) => unit.key === value)
  const visible = showAll ? units : units.slice(0, Math.max(VISIBLE, selectedIndex + 1))

  return (
    <div role="radiogroup" aria-labelledby={labelId} className="grid gap-1.5 sm:grid-cols-2">
      {visible.map((unit) => {
        const label = unitLabel(unit.roomNumber, unit.bedLabel) ?? unit.roomNumber
        const checked = unit.key === value
        return (
          <label
            key={unit.key}
            className={cn(
              'flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 transition-colors',
              'hover:border-border-strong focus-within:ring-2 focus-within:ring-accent/55',
              checked && 'border-accent bg-accent-soft/50 hover:border-accent',
            )}
          >
            <input
              type="radio"
              name={name ?? fallbackName}
              value={unit.key}
              checked={checked}
              onChange={() => onChange(unit.key)}
              data-room={label}
              className="size-4 shrink-0 accent-accent"
            />
            <RoomKeyTag number={label} status={unit.occupiedBy ? 'occupied' : unit.housekeepingStatus} size="sm" />
            <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className={cn('text-[13px] font-semibold', unit.ready ? 'text-fg' : 'text-warning-ink')}>
                {t(`common:status.room.${unit.housekeepingStatus}`)}
              </span>
              {unit.current && <Badge tone="neutral">{t('rooms.assigned')}</Badge>}
              {unit.occupiedBy && (
                <Badge tone="warning" className="max-w-full">
                  <span className="min-w-0 truncate">{t('rooms.occupiedBy', { name: unit.occupiedBy })}</span>
                </Badge>
              )}
              {!unit.sameCategory && (
                <Badge tone="info">
                  {t('rooms.otherCategory')} · {unit.roomTypeCode}
                </Badge>
              )}
            </span>
          </label>
        )
      })}
      {!showAll && units.length > visible.length && (
        <Button variant="link" size="sm" className="justify-self-start" onClick={() => setShowAll(true)}>
          {t('rooms.showAll', { count: units.length })}
        </Button>
      )}
    </div>
  )
}
