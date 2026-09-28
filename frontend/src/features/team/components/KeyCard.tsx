import { Nfc } from 'lucide-react'
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/*
 * The account pages borrow the front desk's key cards. Losing your password is losing your key: the desk
 * encodes a new card and the old ones stop opening doors — exactly what a password reset does to your other
 * sessions. Old cards are hatched like an out-of-service room; the new one wears the accent.
 */

/** The accent card must stay opaque in dark mode, where `--accent-soft` is translucent. */
const ACCENT_FACE: CSSProperties = { background: 'linear-gradient(var(--accent-soft), var(--accent-soft)), var(--surface)' }

type StampTone = 'success' | 'warning' | 'danger'

const STAMP_TONES: Record<StampTone, string> = {
  success: 'border-success text-success-ink',
  warning: 'border-warning text-warning-ink',
  danger: 'border-danger text-danger-ink',
}

/** Rubber stamp on the key sleeve: "Sent", "Verified", "Expired"… */
export function Stamp({ tone, children }: { tone: StampTone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'absolute -right-2 -bottom-3.5 z-20 -rotate-[8deg] rounded-md border-2 bg-surface px-2.5 py-1 text-xs font-extrabold tracking-[0.14em] uppercase shadow-sm',
        'animate-pop-in',
        STAMP_TONES[tone],
      )}
    >
      {children}
    </span>
  )
}

/**
 * A key card filling its (relative, card-shaped) parent. `void` = an old card that no longer opens anything:
 * hatched, with its "Void" label on the top edge (`voidLabel` side), the part that shows behind a newer card.
 */
export function KeyCard({
  tone = 'active',
  title,
  caption,
  voidLabel = 'start',
  className,
}: {
  tone?: 'active' | 'void'
  title?: ReactNode
  caption?: ReactNode
  voidLabel?: 'start' | 'end'
  className?: string
}) {
  const { t } = useTranslation('team')
  if (tone === 'void') {
    return (
      <div
        className={cn(
          'hatch absolute inset-0 overflow-hidden rounded-[18px] border border-border-strong bg-surface-3 p-4 text-stone-ink shadow-md',
          className,
        )}
      >
        <div className={cn('flex items-center justify-between gap-3', voidLabel === 'end' && 'flex-row-reverse')}>
          <span className="rounded-full border border-border-strong bg-surface px-2 py-0.5 text-[11px] font-bold tracking-[0.08em] uppercase">
            {t('scene.void')}
          </span>
          <Nfc aria-hidden className="size-5 opacity-40" />
        </div>
      </div>
    )
  }
  return (
    <div
      style={ACCENT_FACE}
      className={cn(
        'absolute inset-0 flex flex-col justify-between overflow-hidden rounded-[18px] border border-accent/25 p-5 text-accent-ink shadow-md',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="eyebrow !text-accent-ink/80">Housetel</span>
        <Nfc aria-hidden className="size-5 opacity-70" />
      </div>
      <div className="min-w-0">
        <p className="text-[26px] leading-none font-extrabold tracking-[-0.035em]">{title}</p>
        {caption && <p className="num mt-2 truncate text-xs font-semibold text-accent-ink/80">{caption}</p>}
      </div>
    </div>
  )
}

/**
 * The paper sleeve the front desk hands a key card in, with the account written on its line (it follows
 * what the user types). A stamp says what happened to it.
 */
export function KeySleeve({
  account,
  placeholder,
  stamp,
  className,
}: {
  account?: string
  placeholder: string
  stamp?: ReactNode
  className?: string
}) {
  const { t } = useTranslation('team')
  return (
    <div className={cn('relative w-full max-w-[19rem] pt-14', className)}>
      <div aria-hidden style={ACCENT_FACE} className="absolute inset-x-7 top-0 h-32 rounded-[14px] border border-accent/25 p-4 text-accent-ink shadow-sm">
        <div className="flex items-start justify-between">
          <span className="eyebrow !text-accent-ink/80">Housetel</span>
          <Nfc className="size-5 opacity-70" />
        </div>
      </div>
      <div className="relative z-10 rounded-[18px] border border-border-strong bg-surface px-6 pt-6 pb-7 text-left shadow-md">
        <p className="eyebrow">{t('scene.sleeve')}</p>
        <p className="mt-5 eyebrow !text-[10px]">{t('scene.account')}</p>
        <p className="mt-1.5 truncate border-b border-dashed border-border-strong pb-1.5 text-[15px] font-semibold text-fg">
          {account ? account : <span className="font-medium text-subtle">{placeholder}</span>}
        </p>
        {stamp}
      </div>
    </div>
  )
}

/** Reset scene: the new card lands in front of the old ones, which are voided. */
export function RecodeScene({ account }: { account: string }) {
  const { t } = useTranslation('team')
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setSettled(true))
    return () => window.cancelAnimationFrame(frame)
  }, [])

  return (
    <figure className="grid w-full max-w-[21rem] justify-items-center gap-12">
      <div className="relative mt-10 aspect-[1.586] w-full">
        {/* Rotated left, the first card's right corner rises (label there); rotated right, the second's left. */}
        <KeyCard tone="void" voidLabel="end" className="-translate-x-7 -translate-y-12 -rotate-[8deg]" />
        <KeyCard tone="void" className="translate-x-5 -translate-y-7 rotate-[4deg]" />
        <KeyCard
          title={t('scene.newKey')}
          caption={account}
          className={cn(
            'transition-[translate,rotate] duration-700 ease-out motion-reduce:transition-none',
            settled ? '-rotate-2' : 'translate-y-3 -rotate-[7deg]',
          )}
        />
      </div>
      <figcaption className="max-w-xs text-center text-sm text-muted">{t('scene.recodeCaption')}</figcaption>
    </figure>
  )
}
