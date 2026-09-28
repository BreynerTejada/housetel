import { LogIn, LogOut } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { RackRoom } from '../api'
import { groupByFloor, keyState, type KeyAction, type KeyTone } from '../lib/rack'

const TINT: Record<KeyTone, string> = {
  clean: 'bg-room-clean-soft text-success-ink',
  dirty: 'bg-room-dirty-soft text-warning-ink',
  inspected: 'bg-room-inspected-soft text-info-ink',
  occupied: 'bg-room-occupied-soft text-accent-ink',
  blocked: 'bg-room-ooo-soft text-stone-ink hatch',
}

const SWATCH: Record<KeyTone, string> = {
  clean: 'bg-room-clean',
  dirty: 'bg-room-dirty',
  inspected: 'bg-room-inspected',
  occupied: 'bg-room-occupied',
  blocked: 'bg-room-ooo hatch',
}

const LEGEND: { tone: KeyTone; key: string }[] = [
  { tone: 'clean', key: 'common:status.room.clean' },
  { tone: 'dirty', key: 'common:status.room.dirty' },
  { tone: 'inspected', key: 'common:status.room.inspected' },
  { tone: 'occupied', key: 'common:status.room.occupied' },
  { tone: 'blocked', key: 'rack.blocked' },
]

export interface KeyRackProps {
  rooms: RackRoom[]
  /** What the signed-in role may do from a key; keys whose action is not allowed only show their state. */
  can: (action: KeyAction['kind']) => boolean
  onAction: (room: RackRoom, action: KeyAction) => void
}

/**
 * The key rack behind the desk, live (signature of the Today panel): every room tonight as a key tag tinted
 * by its state — occupied, clean, dirty, inspected, blocked — with a marker for the guest arriving or leaving
 * today. A key is also the shortest way to act: check the arrival in, check the departure out, open the
 * guest's reservation, or book a free room.
 */
export function KeyRack({ rooms, can, onAction }: KeyRackProps) {
  const { t } = useTranslation('frontdesk')
  const titleId = useId()
  const floors = groupByFloor(rooms)

  return (
    <section aria-labelledby={titleId} className="rounded-xl border border-border bg-surface p-5 shadow-xs">
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 id={titleId} className="text-[15px] font-bold tracking-[-0.01em]">
          {t('rack.title')}
        </h2>
        <p className="text-[13px] text-muted">{t('rack.tonight')}</p>
      </header>
      {rooms.length === 0 ? (
        <p className="py-6 text-center text-[13px] text-muted">{t('rack.empty')}</p>
      ) : (
        <div className="grid gap-4">
          {floors.map(({ floor, rooms: keys }, index) => (
            <div key={`${floor}-${index}`} className="grid gap-2">
              <span className="eyebrow !text-[10px]">{floor ? t('rack.floor', { floor }) : t('rack.noFloor')}</span>
              <ul className="flex flex-wrap gap-1.5">
                {keys.map((room) => (
                  <li key={room.id}>
                    <RackKey room={room} can={can} onAction={onAction} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <ul className="mt-5 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border pt-3 text-xs text-muted">
        {LEGEND.map(({ tone, key }) => (
          <li key={tone} className="inline-flex items-center gap-1.5">
            <span aria-hidden className={cn('size-2.5 rounded-[3px]', SWATCH[tone])} />
            {t(key)}
          </li>
        ))}
        <li className="inline-flex items-center gap-1.5">
          <LogIn aria-hidden className="size-3 text-info-ink" />
          {t('rack.arriving')}
        </li>
        <li className="inline-flex items-center gap-1.5">
          <LogOut aria-hidden className="size-3" />
          {t('rack.departing')}
        </li>
      </ul>
    </section>
  )
}

function RackKey({ room, can, onAction }: { room: RackRoom; can: KeyRackProps['can']; onAction: KeyRackProps['onAction'] }) {
  const { t } = useTranslation('frontdesk')
  const state = keyState(room)
  const interactive = state.action.kind !== 'none' && can(state.action.kind)
  const facts = [room.number, t(`rack.tone.${state.tone}`)]
  if (room.beds) facts.push(t('rack.beds', { occupied: room.beds.occupied, total: room.beds.total }))
  if (room.occupant) facts.push(t(room.occupant.departing ? 'rack.leaves' : 'rack.stays', { name: room.occupant.guest_name }))
  if (room.arrival) facts.push(t(room.arrival.late ? 'rack.arrivesLate' : 'rack.arrives', { name: room.arrival.guest_name }))
  const description = facts.join(', ')
  const label = interactive ? `${description}: ${t(`rack.action.${state.action.kind}`)}` : description

  const body = (
    <>
      <span aria-hidden className="absolute top-1.5 left-1.5 size-1.5 rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]" />
      {state.arriving && <LogIn aria-hidden className="absolute top-1 right-1 size-3 text-info-ink" />}
      {state.departing && <LogOut aria-hidden className="absolute bottom-1 left-1 size-3" />}
      <span className="num text-[12px] leading-none font-bold">{room.number}</span>
      {room.beds && (
        <span aria-hidden className="num mt-0.5 text-[10px] leading-none font-semibold opacity-80">
          {room.beds.occupied}/{room.beds.total}
        </span>
      )}
    </>
  )
  const classes = cn(
    'relative flex h-11 min-w-14 flex-col items-end justify-end rounded-md px-1.5 pb-1.5',
    TINT[state.tone],
    interactive &&
      'transition-[box-shadow,transform] duration-150 hover:-translate-y-px hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
  )

  return (
    <Tooltip content={description}>
      {interactive ? (
        <button type="button" aria-label={label} data-tone={state.tone} className={classes} onClick={() => onAction(room, state.action)}>
          {body}
        </button>
      ) : (
        <span role="img" aria-label={label} tabIndex={0} data-tone={state.tone} className={cn(classes, 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60')}>
          {body}
        </span>
      )}
    </Tooltip>
  )
}
