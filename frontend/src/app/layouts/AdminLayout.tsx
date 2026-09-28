import { Menu } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router'
import { findActiveNav, useNav } from '@/app/extensions'
import { DemoBanner } from '@/app/shell/DemoBanner'
import { LanguageMenu } from '@/app/shell/LanguageMenu'
import { ThemeMenu } from '@/app/shell/ThemeMenu'
import { UserMenu } from '@/app/shell/UserMenu'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

function AdminNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const items = useNav('admin')
  const activeId = findActiveNav(items, pathname)
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center px-4">
        <Link to="/admin" onClick={onNavigate} aria-label={t('app.name')} className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
          <Logo />
        </Link>
      </div>
      <div className="mx-3 mb-4 rounded-lg border border-accent/25 bg-accent-soft px-3 py-2.5">
        <p className="text-[13px] font-bold text-accent-ink">{t('admin.banner')}</p>
        <p className="text-xs text-muted">{t('admin.bannerHint')}</p>
      </div>
      <nav aria-label={t('nav.adminNav')} className="flex-1 overflow-y-auto px-3">
        <ul className="grid gap-0.5">
          {items.map((item) => {
            const Icon = item.icon
            const active = item.id === activeId
            return (
              <li key={item.id}>
                <Link
                  to={item.path}
                  onClick={onNavigate}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex h-8 items-center gap-2.5 rounded-md px-2 text-[13.5px] font-medium text-muted transition-colors',
                    'hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                    active && 'bg-surface text-fg shadow-xs ring-1 ring-border',
                  )}
                >
                  <Icon aria-hidden className={cn('size-[17px]', active ? 'text-accent' : 'text-subtle')} />
                  {t(item.labelKey)}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </div>
  )
}

/** Platform super-admin shell (`/admin`). */
export function AdminLayout() {
  const { t } = useTranslation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  return (
    <div className="app-shell flex min-h-dvh bg-bg">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-border lg:block">
        <AdminNav />
      </aside>
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent side="left" className="w-[min(18rem,86vw)] bg-bg">
          <SheetTitle className="sr-only">{t('nav.adminNav')}</SheetTitle>
          <SheetDescription className="sr-only">{t('admin.bannerHint')}</SheetDescription>
          <AdminNav onNavigate={() => setDrawerOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBanner />
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-bg/85 px-2 backdrop-blur-md sm:px-4 lg:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t('nav.openMenu')} onClick={() => setDrawerOpen(true)}>
            <Menu aria-hidden />
          </Button>
          <div className="flex-1" />
          <LanguageMenu />
          <ThemeMenu />
          <UserMenu area="admin" />
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
