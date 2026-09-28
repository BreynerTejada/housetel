import { Mail, MapPin, Phone, ShieldCheck, Store } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { LanguageMenu } from '@/app/shell/LanguageMenu'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { LogoMark } from '@/components/Logo'
import { LegalFooterLinks } from '@/features/saas/components/LegalFooterLinks'
import { cn } from '@/lib/utils'
import { useEngineConfig, type EngineConfig } from '../api'
import { useBrandTheme } from '../lib/useBrandTheme'

const GENERIC_WORDS = new Set(['hotel', 'hostal', 'hostel', 'the', 'el', 'la'])

/** "Hotel Casa Aurora" → "CA" (for hotels without a logo). */
function monogram(name: string): string {
  const words = name.split(/\s+/).filter((word) => word && !GENERIC_WORDS.has(word.toLowerCase()))
  return (words.length ? words : name.split(/\s+/))
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

export function HotelMark({ config, className }: { config: Pick<EngineConfig, 'name' | 'logo'>; className?: string }) {
  if (config.logo) return <img src={config.logo} alt="" className={cn('h-9 w-auto max-w-32 object-contain', className)} />
  return (
    <span aria-hidden className={cn('grid size-9 shrink-0 place-items-center rounded-full bg-accent text-sm font-extrabold text-on-accent', className)}>
      {monogram(config.name)}
    </span>
  )
}

export function EngineContact({ config }: { config: EngineConfig }) {
  return (
    <ul className="grid gap-1.5 text-sm">
      {config.address && (
        <li className="flex items-center gap-2 text-muted">
          <MapPin aria-hidden className="size-4 shrink-0" />
          {[config.address, config.city].filter(Boolean).join(', ')}
        </li>
      )}
      {config.phone && (
        <li>
          <a href={`tel:${config.phone.replace(/\s+/g, '')}`} className="inline-flex items-center gap-2 text-fg hover:underline">
            <Phone aria-hidden className="size-4 text-muted" />
            {config.phone}
          </a>
        </li>
      )}
      {config.email && (
        <li>
          <a href={`mailto:${config.email}`} className="inline-flex items-center gap-2 text-fg hover:underline">
            <Mail aria-hidden className="size-4 text-muted" />
            {config.email}
          </a>
        </li>
      )}
    </ul>
  )
}

export function EngineUnavailable({ config }: { config: EngineConfig }) {
  const { t } = useTranslation('marketplace')
  return (
    <div className="mx-auto max-w-lg px-4 py-20 text-center">
      <Store aria-hidden className="mx-auto size-8 text-accent" />
      <h1 className="mt-4 text-2xl font-extrabold tracking-[-0.03em] text-fg">{t('engine.unavailableTitle')}</h1>
      <p className="mt-2 text-muted">{t('engine.unavailableBody')}</p>
      <div className="mt-6 inline-block text-left">
        <EngineContact config={config} />
      </div>
    </div>
  )
}

/**
 * Frame of the hotel's own pages (`/h/:slug…`): the hotel's name, logo and color instead of Housetel's, and a
 * discreet "powered by" at the bottom. Renders its children only while the engine takes bookings.
 */
export function EngineShell({ slug, children }: { slug: string; children: (config: EngineConfig) => ReactNode }) {
  const { t } = useTranslation('marketplace')
  const config = useEngineConfig(slug)
  useBrandTheme(config.data?.primary_color)

  if (config.isPending) return <LoadingState className="min-h-dvh" />
  if (config.isError) {
    return (
      <ErrorState error={config.error} onRetry={() => void config.refetch()} className="min-h-dvh justify-center" />
    )
  }
  const hotel = config.data

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link to={`/h/${slug}`} className="flex min-w-0 items-center gap-3 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
            <HotelMark config={hotel} />
            <span className="truncate text-[17px] font-extrabold tracking-[-0.02em] text-fg">{hotel.name}</span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 text-xs font-semibold text-muted sm:flex">
              <ShieldCheck aria-hidden className="size-4 text-accent" />
              {t('engine.bestRate')}
            </span>
            <LanguageMenu />
          </div>
        </div>
      </header>
      <main className="flex-1">
        {hotel.enabled ? children(hotel) : <EngineUnavailable config={hotel} />}
      </main>
      <footer className="mt-10 border-t border-border bg-surface">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 sm:grid-cols-[1fr_auto] sm:items-end sm:px-6">
          <div>
            <p className="font-bold text-fg">{hotel.name}</p>
            {hotel.enabled && (
              <div className="mt-2">
                <EngineContact config={hotel} />
              </div>
            )}
          </div>
          <div className="grid gap-2 sm:justify-items-end">
            <p className="flex items-center gap-2 text-xs text-muted">
              <LogoMark className="size-5" />
              {t('engine.poweredBy')}
            </p>
            <LegalFooterLinks />
          </div>
        </div>
      </footer>
    </div>
  )
}
