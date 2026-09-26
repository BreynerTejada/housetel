import { PanelLeftClose, PanelLeftOpen, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'
import { findActiveNav, NAV_SECTIONS, useNav, type NavItem, type NavSection } from '@/app/extensions'
import { Logo } from '@/components/Logo'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

const MAIN_SECTIONS: NavSection[] = NAV_SECTIONS.filter((section) => section !== 'settings' && section !== 'admin')

function NavEntry({
  to,
  icon: Icon,
  label,
  active,
  collapsed,
  onNavigate,
}: {
  to: string
  icon: NavItem['icon']
  label: string
  active: boolean
  collapsed: boolean
  onNavigate?: () => void
}) {
  const link = (
    <Link
      to={to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'group flex h-8 items-center gap-2.5 rounded-md px-2 text-[13.5px] font-medium text-muted transition-colors',
        'hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        active && 'bg-surface text-fg shadow-xs ring-1 ring-border hover:bg-surface',
        collapsed && 'justify-center px-0',
      )}
    >
      <Icon aria-hidden className={cn('size-[17px] shrink-0 transition-colors', active ? 'text-accent' : 'text-subtle group-hover:text-muted')} />
      <span className={cn('truncate', collapsed && 'sr-only')}>{label}</span>
    </Link>
  )
  return collapsed ? (
    <Tooltip content={label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  )
}

/** Sidebar contents (desktop aside and mobile drawer): logo, sections, settings entry, collapse toggle. */
export function SidebarNav({
  collapsed = false,
  onToggleCollapsed,
  onNavigate,
}: {
  collapsed?: boolean
  onToggleCollapsed?: () => void
  onNavigate?: () => void
}) {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const items = useNav()
  const mainItems = items.filter((item) => MAIN_SECTIONS.includes(item.section))
  const hasSettings = items.some((item) => item.section === 'settings')
  const activeId = findActiveNav(mainItems, pathname)
  const settingsActive = pathname === '/app/settings' || pathname.startsWith('/app/settings/')

  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex h-14 shrink-0 items-center', collapsed ? 'justify-center' : 'px-4')}>
        <Link to="/app" onClick={onNavigate} aria-label={t('app.name')} className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
          <Logo withWordmark={!collapsed} />
        </Link>
      </div>

      <nav aria-label={t('nav.main')} className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pt-2 pb-3">
          {MAIN_SECTIONS.map((section) => {
            const sectionItems = mainItems.filter((item) => item.section === section)
            if (sectionItems.length === 0) return null
            return (
              <div key={section} className="mb-4">
                {collapsed ? (
                  <div aria-hidden className="mx-auto mb-2 h-px w-6 bg-border" />
                ) : (
                  <p className="eyebrow px-2 pb-1.5">{t(`nav.sections.${section}`)}</p>
                )}
                <ul className="grid gap-0.5">
                  {sectionItems.map((item) => (
                    <li key={item.id}>
                      <NavEntry
                        to={item.path}
                        icon={item.icon}
                        label={t(item.labelKey)}
                        active={item.id === activeId}
                        collapsed={collapsed}
                        onNavigate={onNavigate}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
        {hasSettings && (
          <div className="shrink-0 border-t border-border px-3 py-2">
            <NavEntry
              to="/app/settings"
              icon={Settings}
              label={t('nav.settings')}
              active={settingsActive}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          </div>
        )}
      </nav>

      {onToggleCollapsed && (
        <div className={cn('shrink-0 border-t border-border px-3 py-2', collapsed && 'flex justify-center')}>
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
            className="flex h-8 items-center gap-2 rounded-md px-2 text-[13px] text-subtle transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {collapsed ? <PanelLeftOpen aria-hidden className="size-4" /> : <PanelLeftClose aria-hidden className="size-4" />}
            {!collapsed && <span>{t('nav.collapse')}</span>}
          </button>
        </div>
      )}
    </div>
  )
}
