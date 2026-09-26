import { cn } from '@/lib/utils'

/** The Housetel mark: a terracotta key tag with a punched hole and a lowercase "h". */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn('size-7 shrink-0', className)}>
      <rect width="64" height="64" rx="16" className="fill-accent" />
      <circle cx="48.5" cy="15.5" r="4.25" className="fill-bg" />
      <path
        d="M22 15.5v33M22 35c0-6.2 4.4-10 10-10s10 3.8 10 10v13.5"
        fill="none"
        className="stroke-on-accent"
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo({ className, withWordmark = true }: { className?: string; withWordmark?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <LogoMark />
      {withWordmark && <span className="text-[17px] leading-none font-extrabold tracking-[-0.045em] text-fg">housetel</span>}
    </span>
  )
}
