import { initials } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

const SIZES = {
  sm: 'size-8 rounded-md text-[11px]',
  md: 'size-10 rounded-md text-xs',
  lg: 'size-16 rounded-xl text-xl tracking-[-0.02em]',
}

const HOLES = {
  sm: 'top-1 left-1 size-1',
  md: 'top-1.5 left-1.5 size-1.5',
  lg: 'top-2 left-2 size-2',
}

/**
 * The guest's initials on a key tag — the same punched tag as the front-desk room rack. VIP guests get
 * the warm tag; anonymized guests a blank one.
 */
export function GuestAvatar({
  name,
  vip = false,
  muted = false,
  size = 'md',
  className,
}: {
  name: string
  vip?: boolean
  muted?: boolean
  size?: keyof typeof SIZES
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'relative grid shrink-0 place-items-center border font-bold select-none',
        SIZES[size],
        vip ? 'border-accent/35 bg-accent-soft text-accent-ink' : 'border-border bg-surface-2 text-muted',
        muted && 'hatch border-dashed bg-surface text-subtle',
        className,
      )}
    >
      <span className={cn('absolute rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]', HOLES[size])} />
      <span className="num leading-none">{muted ? '—' : initials(name)}</span>
    </span>
  )
}
