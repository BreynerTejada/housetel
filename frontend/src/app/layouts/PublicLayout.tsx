import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation, useMatches } from 'react-router'
import { LanguageMenu } from '@/app/shell/LanguageMenu'
import { PublicChatSlot } from '@/app/shell/PublicChatSlot'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
// Housetel's legal documents (P6) in the public footer (P-INT). The booking engine and the guest portal, which
// hide this footer, carry the same links in their own.
import { LegalFooterLinks } from '@/features/saas/components/LegalFooterLinks'

interface PublicHandle {
  /** `'none'` hides the Housetel header and footer (hotel-branded pages: booking engine, guest portal). */
  chrome?: 'none'
}

function PublicHeader() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link to="/" aria-label={t('app.name')} className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
          <Logo />
        </Link>
        <nav className="ml-auto flex items-center gap-1 sm:gap-2">
          <Link
            to="/signup"
            className="rounded-md px-2.5 py-1.5 text-sm font-semibold text-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {t('public.forHotels')}
          </Link>
          <LanguageMenu />
          {pathname !== '/login' && (
            <Button asChild size="sm">
              <Link to="/login">{t('public.login')}</Link>
            </Button>
          )}
        </nav>
      </div>
    </header>
  )
}

function PublicFooter() {
  const { t } = useTranslation()
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-3">
          <Logo withWordmark={false} />
          <p>{t('public.footerTagline')}</p>
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <LegalFooterLinks docs={['terminos', 'privacidad', 'encargo-datos']} className="text-sm" />
          <p className="num">
            {t('public.rights', { year: new Date().getFullYear() })} · {t('public.madeIn')}
          </p>
        </div>
      </div>
    </footer>
  )
}

/** Marketplace, login and other public pages: 16px editorial base, header, footer and the chat slot. */
export function PublicLayout() {
  const matches = useMatches()
  const { pathname } = useLocation()
  const bare = matches.some((match) => (match.handle as PublicHandle | undefined)?.chrome === 'none')
  const params = matches.at(-1)?.params ?? {}
  // Only the guest portal's `/g/:token` is a portal token: other public routes also call their secret `token`
  // (`/invite/:token`), and it must not travel to the chat API (P2 → P-INT).
  const portalToken = pathname.startsWith('/g/') ? params.token : undefined
  return (
    <div className="public-shell flex min-h-dvh flex-col bg-bg">
      {!bare && <PublicHeader />}
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
      {!bare && <PublicFooter />}
      <PublicChatSlot propertySlug={params.slug} portalToken={portalToken} />
    </div>
  )
}
