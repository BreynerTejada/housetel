import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useReducedMotion } from '@/lib/hooks'
import { cn } from '@/lib/utils'

type RoomState = 'occupied' | 'dirty' | 'clean' | 'inspected' | 'ooo'

// Casa Aurora, the demo hotel: 24 rooms on three floors (spec §10).
const FLOORS: { floor: number; rooms: string[]; pattern: string }[] = [
  { floor: 3, rooms: ['301', '302', '303', '304', '305', '306'], pattern: 'OOCOIO' },
  { floor: 2, rooms: ['201', '202', '203', '204', '205', '206', '207', '208'], pattern: 'OODOOCOI' },
  { floor: 1, rooms: ['101', '102', '103', '104', '105', '106', '107', '108', '109', '110'], pattern: 'OCOODOXOIO' },
]

const FROM_CODE: Record<string, RoomState> = { O: 'occupied', D: 'dirty', C: 'clean', I: 'inspected', X: 'ooo' }
/** A day at the front desk: check-out → housekeeping → inspection → next check-in. */
const NEXT: Record<RoomState, RoomState> = { occupied: 'dirty', dirty: 'clean', clean: 'inspected', inspected: 'occupied', ooo: 'ooo' }

const SLOT: Record<RoomState, string> = {
  occupied: 'bg-room-occupied-soft text-accent-ink',
  dirty: 'bg-room-dirty-soft text-warning-ink',
  clean: 'bg-room-clean-soft text-success-ink',
  inspected: 'bg-room-inspected-soft text-info-ink',
  ooo: 'bg-room-ooo-soft text-stone-ink hatch',
}

const SWATCH: Record<RoomState, string> = {
  occupied: 'bg-room-occupied',
  dirty: 'bg-room-dirty',
  clean: 'bg-room-clean',
  inspected: 'bg-room-inspected',
  ooo: 'bg-room-ooo',
}

const LEGEND: { state: RoomState; key: string }[] = [
  { state: 'clean', key: 'status.room.clean' },
  { state: 'dirty', key: 'status.room.dirty' },
  { state: 'inspected', key: 'status.room.inspected' },
  { state: 'occupied', key: 'status.room.occupied' },
  { state: 'ooo', key: 'status.room.out_of_service' },
]

/** Index of each floor's first room in the flat state list. */
const FLOOR_STARTS = FLOORS.map((_, index) => FLOORS.slice(0, index).reduce((sum, floor) => sum + floor.rooms.length, 0))

const initialStates = () => FLOORS.flatMap(({ pattern }) => [...pattern].map((code) => FROM_CODE[code] ?? 'occupied'))

/**
 * The front-desk room rack, drawn as key tags in the room-state colors. One tag moves along the
 * housekeeping cycle every few seconds; it stays still for people who prefer reduced motion.
 */
export function RoomRack() {
  const { t } = useTranslation()
  const reducedMotion = useReducedMotion()
  const [states, setStates] = useState<RoomState[]>(initialStates)

  useEffect(() => {
    if (reducedMotion) return
    let seed = 7
    const id = window.setInterval(() => {
      seed = (seed * 37 + 11) % 97
      setStates((current) => {
        const movable = current.map((state, index) => (state === 'ooo' ? -1 : index)).filter((index) => index >= 0)
        const target = movable[seed % movable.length]
        if (target === undefined) return current
        return current.map((state, index) => (index === target ? NEXT[state] : state))
      })
    }, 2600)
    return () => window.clearInterval(id)
  }, [reducedMotion])

  return (
    <figure className="grid gap-5">
      <div role="img" aria-label={t('auth.rackLabel')} className="grid gap-4">
        {FLOORS.map(({ floor, rooms }, floorIndex) => {
          const start = FLOOR_STARTS[floorIndex] ?? 0
          return (
            <div key={floor} className="grid gap-2 border-b border-border/80 pb-4 last:border-0 last:pb-0">
              <span className="eyebrow !text-[10px]">{t('auth.floor', { floor })}</span>
              {/* One column per slot, like a real rack: floors with fewer rooms leave empty slots. */}
              <ul className="grid grid-cols-10 gap-1.5">
                {rooms.map((room, i) => {
                  const state = states[start + i] ?? 'occupied'
                  return (
                    <li
                      key={room}
                      className={cn(
                        'relative flex h-10 items-end justify-end rounded-md px-1.5 pb-1 transition-colors duration-700',
                        SLOT[state],
                      )}
                    >
                      <span aria-hidden className="absolute top-1.5 left-1.5 size-1.5 rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]" />
                      <span className="num text-[11px] leading-none font-bold">{room}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
      <figcaption>
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
          {LEGEND.map(({ state, key }) => (
            <li key={state} className="inline-flex items-center gap-1.5">
              <span aria-hidden className={cn('size-2.5 rounded-[3px]', SWATCH[state], state === 'ooo' && 'hatch')} />
              {t(key)}
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  )
}
