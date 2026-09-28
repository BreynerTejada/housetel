import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

const MAX_TAGS = 60

/**
 * The rooms of one category as key tags on the front-desk rack (the same tags as the login's room rack):
 * dashed and unhung while the proposal is being reviewed, hung in the "clean" color once the rooms exist.
 * Hanging is the one orchestrated motion of the flow: the tags drop in one after another (instant for people
 * who prefer reduced motion).
 */
export function KeyTags({
  rooms,
  label,
  hung = false,
  busy = false,
}: {
  rooms: string[]
  label: string
  hung?: boolean
  busy?: boolean
}) {
  const { t } = useTranslation('ai')
  const shown = rooms.slice(0, MAX_TAGS)
  return (
    <ul aria-label={label} aria-busy={busy || undefined} className={cn('flex flex-wrap gap-1.5', busy && 'opacity-60')}>
      {shown.map((room, index) => (
        <li
          key={room}
          style={hung ? { animationDelay: `${Math.min(index, 30) * 40}ms` } : undefined}
          className={cn(
            'relative flex h-10 w-12 items-end justify-end rounded-md px-1.5 pb-1 transition-colors duration-500',
            hung
              ? 'bg-room-clean-soft text-success-ink [animation-fill-mode:both] motion-safe:animate-pop-in'
              : 'border border-dashed border-border-strong bg-surface-2 text-muted',
          )}
        >
          <span
            aria-hidden
            className="absolute top-1.5 left-1.5 size-1.5 rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]"
          />
          <span className="num text-[11px] leading-none font-bold">{room}</span>
        </li>
      ))}
      {rooms.length > shown.length && (
        <li className="flex h-10 items-center px-1 text-xs font-semibold text-muted">
          {t('onboarding.moreRooms', { count: rooms.length - shown.length })}
        </li>
      )}
    </ul>
  )
}
