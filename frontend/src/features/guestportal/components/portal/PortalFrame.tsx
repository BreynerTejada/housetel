import { useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { currentLanguage, LANGUAGES, setLanguage } from '@/lib/i18n'
import { useTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'
import type { PortalProperty } from '../../api'
import { brandStyle } from '../../lib/brand'
import { hotelInitials } from '../../lib/text'

/**
 * Root of every guest page: wears the hotel's color (accent variables overridden on this subtree, contrast
 * checked for the current theme) so buttons, focus rings and badges follow the hotel, not Housetel.
 */
export function PortalFrame({ property, children, className }: { property?: PortalProperty; children: ReactNode; className?: string }) {
  const { resolvedTheme } = useTheme()
  return (
    // bottom padding = the hotel's chat bubble (when it is on), so the last button can scroll above it
    <div className={cn('flex min-h-dvh flex-1 flex-col bg-bg pb-[var(--public-chat-inset,0px)]', className)} style={brandStyle(property?.primary_color, resolvedTheme)}>
      {children}
    </div>
  )
}

/** The hotel's logo, or its initials on the brand color. */
export function HotelMark({ property, size = 'md' }: { property: PortalProperty; size?: 'sm' | 'md' }) {
  const box = size === 'sm' ? 'size-8 rounded-lg text-xs' : 'size-10 rounded-xl text-sm'
  if (property.logo) {
    return <img src={property.logo} alt="" className={cn(box, 'shrink-0 bg-surface object-contain p-1 shadow-xs')} />
  }
  return (
    <span aria-hidden className={cn(box, 'grid shrink-0 place-items-center bg-accent font-extrabold text-on-accent shadow-xs')}>
      {hotelInitials(property.name)}
    </span>
  )
}

/** ES | EN switch for guests (no account: the choice stays on this device). */
export function LanguageToggle({ tone = 'surface' }: { tone?: 'surface' | 'overlay' }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const active = currentLanguage()
  return (
    <div
      role="group"
      aria-label={t('topbar.language')}
      className={cn(
        'inline-flex rounded-md p-0.5 text-xs font-bold',
        tone === 'overlay' ? 'bg-black/35 text-white backdrop-blur-sm' : 'border border-border bg-surface',
      )}
    >
      {LANGUAGES.map((lang) => (
        <button
          key={lang}
          type="button"
          lang={lang}
          aria-label={t(`languages.${lang}`)}
          aria-pressed={active === lang}
          onClick={() => void setLanguage(lang, queryClient)}
          className={cn(
            'min-w-8 rounded px-2 py-1 uppercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
            tone === 'overlay'
              ? active === lang
                ? 'bg-white/90 text-[#1f1c19]'
                : 'text-white/85 hover:text-white'
              : active === lang
                ? 'bg-surface-3 text-fg'
                : 'text-muted hover:text-fg',
          )}
        >
          {lang}
        </button>
      ))}
    </div>
  )
}

/** Plain top bar of the guest pages without a photo band (the check-in stepper). */
export function PortalTopBar({ property, children }: { property: PortalProperty; children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-bg/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-2xl items-center gap-3 px-4 sm:px-6">
        {children}
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <HotelMark property={property} size="sm" />
          <p className="truncate text-[15px] font-bold tracking-[-0.01em]">{property.name}</p>
        </div>
        <LanguageToggle />
      </div>
    </header>
  )
}
