import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router'
import { findActiveNav, useNav } from '@/app/extensions'
import { cn } from '@/lib/utils'

const SETTINGS_ROOT = '/app/settings'

/** Settings: the index shows every section; section pages get a secondary nav next to them. */
export function SettingsLayout() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const items = useNav('settings')
  if (pathname.replace(/\/$/, '') === SETTINGS_ROOT) return <Outlet />
  const activeId = findActiveNav(items, pathname)

  return (
    <div className="grid gap-6 lg:grid-cols-[13.5rem_minmax(0,1fr)] xl:gap-10">
      <nav aria-label={t('nav.settingsNav')} className="min-w-0 lg:sticky lg:top-20 lg:self-start">
        <Link to={SETTINGS_ROOT} className="eyebrow mb-2 inline-block rounded-sm px-2 hover:text-fg">
          {t('nav.settings')}
        </Link>
        <ul className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0">
          {items.map((item) => {
            const Icon = item.icon
            const active = item.id === activeId
            return (
              <li key={item.id} className="shrink-0">
                <Link
                  to={item.path}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex h-8 items-center gap-2 rounded-md px-2 text-[13px] font-medium whitespace-nowrap text-muted transition-colors',
                    'hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                    active && 'bg-surface text-fg shadow-xs ring-1 ring-border',
                  )}
                >
                  <Icon aria-hidden className={cn('size-4 shrink-0', active ? 'text-accent' : 'text-subtle')} />
                  {t(item.labelKey)}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
      <div className="min-w-0">
        <Outlet />
      </div>
    </div>
  )
}
