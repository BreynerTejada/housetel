import { Menu } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet } from 'react-router'
import { useTopbarItems } from '@/app/extensions'
import { BusinessDateChip } from '@/app/shell/BusinessDateChip'
import { LanguageMenu } from '@/app/shell/LanguageMenu'
import { NoProperties } from '@/app/shell/NoProperties'
import { PropertySwitcher } from '@/app/shell/PropertySwitcher'
import { SearchButton } from '@/app/shell/SearchButton'
import { SidebarNav } from '@/app/shell/SidebarNav'
import { ThemeMenu } from '@/app/shell/ThemeMenu'
import { UserMenu } from '@/app/shell/UserMenu'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { useActiveProperty, useMe } from '@/lib/auth'
import { useHotkey, useLocalStorageState, useMediaQuery } from '@/lib/hooks'
import i18n, { currentLanguage, isLanguage } from '@/lib/i18n'
import { cn } from '@/lib/utils'

const loadCommandPalette = () => import('@/components/CommandPalette')
const CommandPalette = lazy(() => loadCommandPalette().then((m) => ({ default: m.CommandPalette })))

/** Staff shell: collapsible sidebar (drawer on mobile), topbar and the page outlet. */
export function AppLayout() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const { property, synced } = useActiveProperty()
  const topbarItems = useTopbarItems()
  const [collapsed, setCollapsed] = useLocalStorageState('housetel.sidebar.collapsed', false)
  // Phones: the business date goes under the hotel name; language and theme move to the account menu.
  const isPhone = useMediaQuery('(max-width: 639px)')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteMounted, setPaletteMounted] = useState(false)

  function openPalette(open: boolean) {
    if (open) setPaletteMounted(true)
    setPaletteOpen(open)
  }

  useHotkey('k', () => openPalette(!paletteOpen), { mod: true })

  // ⌘K should feel instant: fetch the palette chunk once the browser is idle.
  useEffect(() => {
    if (typeof window.requestIdleCallback !== 'function') return
    const id = window.requestIdleCallback(() => void loadCommandPalette())
    return () => window.cancelIdleCallback(id)
  }, [])

  // The profile language wins when the app loads; later changes go through setLanguage (which saves it).
  const profileLanguage = me?.language
  useEffect(() => {
    if (isLanguage(profileLanguage) && profileLanguage !== currentLanguage()) void i18n.changeLanguage(profileLanguage)
  }, [profileLanguage])

  if (!property) return <NoProperties />

  return (
    <div className="app-shell flex min-h-dvh bg-bg">
      <aside
        className={cn(
          'sticky top-0 hidden h-dvh shrink-0 border-r border-border bg-bg transition-[width] duration-200 lg:block',
          collapsed ? 'w-[68px]' : 'w-60',
        )}
      >
        <SidebarNav collapsed={collapsed} onToggleCollapsed={() => setCollapsed((value) => !value)} />
      </aside>

      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent side="left" className="w-[min(18rem,86vw)] bg-bg">
          <SheetTitle className="sr-only">{t('nav.main')}</SheetTitle>
          <SheetDescription className="sr-only">{property.name}</SheetDescription>
          <SidebarNav onNavigate={() => setDrawerOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-1.5 border-b border-border bg-bg/85 px-2 backdrop-blur-md sm:gap-2 sm:px-4 lg:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t('nav.openMenu')} onClick={() => setDrawerOpen(true)}>
            <Menu aria-hidden />
          </Button>
          <PropertySwitcher />
          {!isPhone && <BusinessDateChip />}
          <div className="hidden flex-1 sm:block" />
          <SearchButton onClick={() => openPalette(true)} />
          {topbarItems.map(({ id, Component }) => (
            <Component key={id} />
          ))}
          {!isPhone && (
            <>
              <LanguageMenu />
              <ThemeMenu />
            </>
          )}
          <UserMenu />
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{synced ? <Outlet /> : <LoadingState />}</main>
      </div>

      {paletteMounted && (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onOpenChange={openPalette} />
        </Suspense>
      )}
    </div>
  )
}
