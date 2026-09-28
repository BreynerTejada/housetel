/**
 * Frontend extension points (plan §E). Features register themselves by exporting well-known names
 * from well-known files inside `src/features/<feature>/`; nobody edits a central file:
 *
 *   routes.tsx               export const routes: FeatureRoutes
 *   nav.ts                   export const nav: NavItem[]
 *   locales/{es,en}.json     i18n namespace = folder name (see src/lib/i18n)
 *   widgets.tsx              export const widgets: DashboardWidget[]          (Today panel, C1)
 *   reservation-tabs.tsx     export const reservationTabs: ReservationTab[]   (reservation detail, C1)
 *   reservation-actions.tsx  export const reservationActions: ReservationAction[]
 *   guest-tabs.tsx           export const guestTabs: GuestTab[]               (guest profile, B3)
 *   topbar.tsx               export const topbarItems: TopbarItem[]           (app topbar)
 *   commands.ts              export const commands: CommandItem[]             (⌘K palette)
 *   public-widget.tsx        export default function PublicWidget(...)       (only `ai`, public layouts)
 */
import type { ComponentType } from 'react'
import { useMemo } from 'react'
import type { RouteObject } from 'react-router'
import type { LucideIcon } from 'lucide-react'
import { useMe } from '@/lib/auth'
import { usePermissionChecker } from '@/lib/permissions'

export type NavSection = 'operations' | 'revenue' | 'insights' | 'compliance' | 'tools' | 'settings' | 'admin'

/** Sidebar order of the sections. */
export const NAV_SECTIONS: NavSection[] = ['operations', 'revenue', 'insights', 'compliance', 'tools', 'settings', 'admin']

export interface NavItem {
  id: string
  section: NavSection
  /** `<feature>:<key>`, e.g. `calendar:nav.calendar`. */
  labelKey: string
  icon: LucideIcon
  /** Absolute path (`/app/...` or `/admin/...`). */
  path: string
  permission?: string
  order?: number
  platformAdmin?: boolean
  /** Optional one-line description (shown on the settings index). */
  descriptionKey?: string
}

/**
 * Route groups. `app` paths are relative to `/app` (`'calendar'`, `'settings/rooms'`; the Today page is
 * `{ index: true }`), `admin` relative to `/admin`, `public`/`bare` absolute. Every `app` route whose path
 * starts with `settings/` is nested in the settings layout. `public` routes render inside PublicLayout;
 * add `handle: { chrome: 'none' }` to hide the Housetel header/footer (hotel-branded pages).
 */
export interface FeatureRoutes {
  public?: RouteObject[]
  app?: RouteObject[]
  admin?: RouteObject[]
  bare?: RouteObject[]
}

export interface DashboardWidget {
  id: string
  order: number
  size: 'sm' | 'md' | 'lg' | 'full'
  permission?: string
  Component: ComponentType
}

export interface ReservationTab {
  id: string
  labelKey: string
  order: number
  permission?: string
  Component: ComponentType<{ reservationId: string }>
}

/**
 * Item of the reservation's actions menu (C1). The host wraps `Component` in its own dialog titled with
 * `labelKey`, so the component renders only the dialog's body (and, if it needs one, a `DialogFooter`) — never
 * a `Dialog` of its own — and calls `close()` when it is done.
 */
export interface ReservationAction {
  id: string
  labelKey: string
  icon: LucideIcon
  order: number
  permission?: string
  danger?: boolean
  Component: ComponentType<{ reservationId: string; close: () => void }>
}

export interface GuestTab {
  id: string
  labelKey: string
  order: number
  permission?: string
  Component: ComponentType<{ guestId: string }>
}

export interface TopbarItem {
  id: string
  order: number
  permission?: string
  Component: ComponentType
}

export interface CommandContext {
  navigate: (to: string) => void
  /** Text typed in the palette when the command ran (e.g. "Ask the copilot…" uses it). */
  query?: string
}

export interface CommandItem {
  id: string
  group: string
  labelKey: string
  icon?: LucideIcon
  keywords?: string[]
  permission?: string
  perform: (ctx: CommandContext) => void
}

export interface PublicWidgetProps {
  propertySlug?: string
  portalToken?: string
}

// ---- Pure collectors (tested with fixture modules) ----------------------------------------------

type Modules<T> = Record<string, T>
type Permission = (code?: string) => boolean

function sectionIndex(section: NavSection): number {
  const index = NAV_SECTIONS.indexOf(section)
  return index === -1 ? NAV_SECTIONS.length : index
}

export function sortNav(items: NavItem[]): NavItem[] {
  return [...items].sort(
    (a, b) => sectionIndex(a.section) - sectionIndex(b.section) || (a.order ?? 1000) - (b.order ?? 1000),
  )
}

export function collectNav(modules: Modules<{ nav?: NavItem[] }>): NavItem[] {
  return sortNav(Object.values(modules).flatMap((module) => module.nav ?? []))
}

export function filterNav(items: NavItem[], { can, isPlatformAdmin }: { can: Permission; isPlatformAdmin: boolean }): NavItem[] {
  return items.filter((item) => (item.platformAdmin ? isPlatformAdmin : can(item.permission)))
}

/**
 * Id of the nav item for `pathname`: the longest item path that is a whole-segment prefix, so detail
 * pages keep their list item active. Root items (`/app`, `/admin`) only match exactly.
 */
export function findActiveNav(items: NavItem[], pathname: string): string | undefined {
  let best: NavItem | undefined
  for (const item of items) {
    const isRoot = item.path.split('/').filter(Boolean).length <= 1
    const matches = pathname === item.path || (!isRoot && pathname.startsWith(`${item.path}/`))
    if (matches && (!best || item.path.length > best.path.length)) best = item
  }
  return best?.id
}

export function collectRoutes(modules: Modules<{ routes?: FeatureRoutes }>): Required<FeatureRoutes> {
  const merged: Required<FeatureRoutes> = { public: [], app: [], admin: [], bare: [] }
  for (const { routes } of Object.values(modules)) {
    if (!routes) continue
    merged.public.push(...(routes.public ?? []))
    merged.app.push(...(routes.app ?? []))
    merged.admin.push(...(routes.admin ?? []))
    merged.bare.push(...(routes.bare ?? []))
  }
  return merged
}

const SETTINGS_PREFIX = 'settings/'

/** Splits `app` routes into the main outlet and the settings layout (paths made relative to it). */
export function splitSettingsRoutes(app: RouteObject[]): { main: RouteObject[]; settings: RouteObject[] } {
  const main: RouteObject[] = []
  const settings: RouteObject[] = []
  for (const route of app) {
    if (route.path?.startsWith(SETTINGS_PREFIX)) {
      settings.push({ ...route, path: route.path.slice(SETTINGS_PREFIX.length) } as RouteObject)
    } else {
      main.push(route)
    }
  }
  return { main, settings }
}

/** Flattens a named array export from every module and sorts it by `order`. */
export function collectItems<K extends string, T extends { order: number }>(
  modules: Modules<Partial<Record<K, T[]>>>,
  exportName: K,
): T[] {
  return Object.values(modules)
    .flatMap((module) => module[exportName] ?? [])
    .sort((a, b) => a.order - b.order)
}

export function visibleItems<T extends { permission?: string }>(items: T[], can: Permission): T[] {
  return items.filter((item) => can(item.permission))
}

// ---- Discovery (Vite globs, eager so routes and nav exist at startup) --------------------------

const navModules = import.meta.glob<{ nav?: NavItem[] }>('../features/*/nav.ts', { eager: true })
const routeModules = import.meta.glob<{ routes?: FeatureRoutes }>('../features/*/routes.tsx', { eager: true })
const widgetModules = import.meta.glob<{ widgets?: DashboardWidget[] }>('../features/*/widgets.tsx', { eager: true })
const reservationTabModules = import.meta.glob<{ reservationTabs?: ReservationTab[] }>(
  '../features/*/reservation-tabs.tsx',
  { eager: true },
)
const reservationActionModules = import.meta.glob<{ reservationActions?: ReservationAction[] }>(
  '../features/*/reservation-actions.tsx',
  { eager: true },
)
const guestTabModules = import.meta.glob<{ guestTabs?: GuestTab[] }>('../features/*/guest-tabs.tsx', { eager: true })
const topbarModules = import.meta.glob<{ topbarItems?: TopbarItem[] }>('../features/*/topbar.tsx', { eager: true })
const commandModules = import.meta.glob<{ commands?: CommandItem[] }>('../features/*/commands.ts', { eager: true })

const allNav = collectNav(navModules)
const allRoutes = collectRoutes(routeModules)
const allWidgets = collectItems(widgetModules, 'widgets')
const allReservationTabs = collectItems(reservationTabModules, 'reservationTabs')
const allReservationActions = collectItems(reservationActionModules, 'reservationActions')
const allGuestTabs = collectItems(guestTabModules, 'guestTabs')
const allTopbarItems = collectItems(topbarModules, 'topbarItems')
const allCommands = Object.values(commandModules).flatMap((module) => module.commands ?? [])

/** Every nav item of every feature, sorted by section and order (not filtered by permission). */
export function getNav(): NavItem[] {
  return allNav
}

export function getFeatureRoutes(): Required<FeatureRoutes> {
  return allRoutes
}

// ---- Hooks (filtered by the active membership's permissions) -----------------------------------

/** Nav items the current user can see, optionally for one section. */
export function useNav(section?: NavSection): NavItem[] {
  const can = usePermissionChecker()
  const { data: me } = useMe()
  const isPlatformAdmin = me?.is_platform_admin ?? false
  return useMemo(
    () => filterNav(allNav, { can, isPlatformAdmin }).filter((item) => !section || item.section === section),
    [can, isPlatformAdmin, section],
  )
}

function useVisible<T extends { permission?: string }>(items: T[]): T[] {
  const can = usePermissionChecker()
  return useMemo(() => visibleItems(items, can), [items, can])
}

export const useWidgets = () => useVisible(allWidgets)
export const useReservationTabs = () => useVisible(allReservationTabs)
export const useReservationActions = () => useVisible(allReservationActions)
export const useGuestTabs = () => useVisible(allGuestTabs)
export const useTopbarItems = () => useVisible(allTopbarItems)
export const useCommands = () => useVisible(allCommands)
