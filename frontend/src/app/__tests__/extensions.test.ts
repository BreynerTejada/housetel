import type { RouteObject } from 'react-router'
import { describe, expect, it } from 'vitest'
import {
  collectItems,
  collectNav,
  collectRoutes,
  filterNav,
  findActiveNav,
  getFeatureRoutes,
  getNav,
  NAV_SECTIONS,
  splitSettingsRoutes,
  visibleItems,
  type NavItem,
} from '@/app/extensions'

const Icon = (() => null) as unknown as NavItem['icon']

// Plan §E / Task A2 Step 6: `id · section · path · permission` for the 18 features.
const EXPECTED_NAV: [string, string, string, string, string | undefined, boolean?][] = [
  ['frontdesk', 'today', 'operations', '/app', 'frontdesk.view'],
  ['frontdesk', 'reservations', 'operations', '/app/reservations', 'bookings.view'],
  ['frontdesk', 'nightAudit', 'tools', '/app/night-audit', 'frontdesk.night_audit'],
  ['calendar', 'calendar', 'operations', '/app/calendar', 'bookings.view'],
  ['guests', 'guests', 'operations', '/app/guests', 'guests.view'],
  ['housekeeping', 'housekeeping', 'operations', '/app/housekeeping', 'housekeeping.view'],
  ['housekeeping', 'maintenance', 'operations', '/app/maintenance', 'housekeeping.view'],
  ['housekeeping', 'settingsHousekeeping', 'settings', '/app/settings/housekeeping', 'housekeeping.supervise'],
  ['messaging', 'inbox', 'operations', '/app/inbox', 'messaging.view'],
  ['messaging', 'waSim', 'tools', '/app/simulators/whatsapp', 'messaging.send'],
  ['messaging', 'settingsMessaging', 'settings', '/app/settings/messaging', 'messaging.templates'],
  ['finance', 'cashier', 'operations', '/app/cashier', 'finance.view'],
  ['rates', 'rates', 'revenue', '/app/rates', 'rates.view'],
  ['rates', 'ratePlans', 'revenue', '/app/rates/plans', 'rates.view'],
  ['rates', 'promos', 'revenue', '/app/rates/promos', 'rates.view'],
  ['rates', 'taxes', 'settings', '/app/settings/taxes', 'rates.manage'],
  ['rates', 'policies', 'settings', '/app/settings/policies', 'rates.manage'],
  ['rates', 'extras', 'settings', '/app/settings/extras', 'rates.manage'],
  ['revenue', 'revenue', 'revenue', '/app/revenue', 'revenue.view'],
  ['channels', 'channels', 'revenue', '/app/channels', 'distribution.view'],
  ['channels', 'otaSim', 'tools', '/app/simulators/ota', 'distribution.manage'],
  ['reports', 'reports', 'insights', '/app/reports', 'reports.operational'],
  ['control', 'alerts', 'insights', '/app/alerts', 'control.alerts'],
  ['control', 'integrations', 'settings', '/app/settings/integrations', 'control.integrations'],
  ['control', 'automations', 'settings', '/app/settings/automations', 'control.automations'],
  ['control', 'audit', 'settings', '/app/settings/audit', 'control.audit'],
  ['compliance', 'compliance', 'compliance', '/app/compliance', 'compliance.view'],
  ['compliance', 'settingsCompliance', 'settings', '/app/settings/compliance', 'compliance.settings'],
  ['inventory', 'property', 'settings', '/app/settings/property', 'inventory.manage'],
  ['inventory', 'roomTypes', 'settings', '/app/settings/room-types', 'inventory.view'],
  ['inventory', 'rooms', 'settings', '/app/settings/rooms', 'inventory.view'],
  ['inventory', 'customFields', 'settings', '/app/settings/custom-fields', 'inventory.manage'],
  ['team', 'users', 'settings', '/app/settings/users', 'accounts.users_manage'],
  ['team', 'roles', 'settings', '/app/settings/roles', 'accounts.roles_manage'],
  ['marketplace', 'bookingEngine', 'settings', '/app/settings/booking-engine', 'marketplace.manage'],
  ['guestportal', 'guestPortal', 'settings', '/app/settings/guest-portal', 'guestportal.manage'],
  ['ai', 'onboarding', 'tools', '/app/onboarding', 'ai.onboarding'],
  ['ai', 'chatbot', 'settings', '/app/settings/chatbot', 'ai.settings'],
  ['ai', 'aiSettings', 'settings', '/app/settings/ai', 'ai.settings'],
  ['saas', 'gettingStarted', 'tools', '/app/getting-started', undefined],
  ['saas', 'billing', 'settings', '/app/settings/billing', 'saas.billing_view'],
  ['saas', 'adminHome', 'admin', '/admin', undefined, true],
  ['saas', 'adminOrgs', 'admin', '/admin/organizations', undefined, true],
  ['saas', 'adminPlans', 'admin', '/admin/plans', undefined, true],
  ['saas', 'adminBilling', 'admin', '/admin/billing', undefined, true],
  ['saas', 'adminCommissions', 'admin', '/admin/commissions', undefined, true],
]

describe('nav discovery (real feature stubs)', () => {
  const nav = getNav()

  it('finds every nav item of the 18 features with its section, path and permission', () => {
    const actual = nav
      .map((item) => [item.labelKey.split(':')[0], item.id, item.section, item.path, item.permission, item.platformAdmin ?? false])
      .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
    const expected = EXPECTED_NAV.map(([feature, id, section, path, permission, admin]) => [
      feature,
      id,
      section,
      path,
      permission,
      admin ?? false,
    ]).sort((a, b) => String(a[1]).localeCompare(String(b[1])))

    expect(actual).toEqual(expected)
    expect(new Set(nav.map((item) => item.labelKey.split(':')[0])).size).toBe(18)
  })

  it('uses unique ids', () => {
    expect(new Set(nav.map((item) => item.id)).size).toBe(nav.length)
  })

  it('orders items by section, then by order', () => {
    const sectionIndexes = nav.map((item) => NAV_SECTIONS.indexOf(item.section))
    expect(sectionIndexes).toEqual([...sectionIndexes].sort((a, b) => a - b))
    const operations = nav.filter((item) => item.section === 'operations').map((item) => item.id)
    expect(operations.slice(0, 3)).toEqual(['today', 'calendar', 'reservations'])
  })
})

describe('filterNav', () => {
  const items: NavItem[] = [
    { id: 'a', section: 'operations', labelKey: 'x:a', icon: Icon, path: '/app', permission: 'frontdesk.view' },
    { id: 'b', section: 'operations', labelKey: 'x:b', icon: Icon, path: '/app/housekeeping', permission: 'housekeeping.view' },
    { id: 'c', section: 'tools', labelKey: 'x:c', icon: Icon, path: '/app/getting-started' },
    { id: 'd', section: 'admin', labelKey: 'x:d', icon: Icon, path: '/admin', platformAdmin: true },
  ]
  const housekeeper = (code?: string) => !code || ['housekeeping.view', 'housekeeping.work'].includes(code)

  it('keeps items the user has permission for and those without a permission', () => {
    expect(filterNav(items, { can: housekeeper, isPlatformAdmin: false }).map((i) => i.id)).toEqual(['b', 'c'])
  })

  it('shows platform items only to platform admins', () => {
    expect(filterNav(items, { can: housekeeper, isPlatformAdmin: true }).map((i) => i.id)).toEqual(['b', 'c', 'd'])
  })
})

describe('collectNav', () => {
  it('flattens nav from every module and sorts by section then order', () => {
    const nav = collectNav({
      '../features/zeta/nav.ts': {
        nav: [
          { id: 'z2', section: 'settings', labelKey: 'zeta:z2', icon: Icon, path: '/app/settings/z', order: 1 },
          { id: 'z1', section: 'operations', labelKey: 'zeta:z1', icon: Icon, path: '/app/z', order: 50 },
        ],
      },
      '../features/alpha/nav.ts': {
        nav: [{ id: 'a1', section: 'operations', labelKey: 'alpha:a1', icon: Icon, path: '/app/a', order: 10 }],
      },
      '../features/empty/nav.ts': {},
    })
    expect(nav.map((item) => item.id)).toEqual(['a1', 'z1', 'z2'])
  })
})

describe('routes', () => {
  it('merges the route groups of every feature stub', () => {
    const routes = getFeatureRoutes()
    const paths = (list: RouteObject[]) => list.map((route) => (route.index ? '(index)' : route.path))

    expect(paths(routes.public)).toEqual(expect.arrayContaining(['/', '/search', '/hotel/:slug', '/signup', '/invite/:token', '/g/:token']))
    expect(paths(routes.bare)).toEqual(expect.arrayContaining(['/sim/pay/:reference', '/embed/:slug']))
    expect(paths(routes.app)).toEqual(
      expect.arrayContaining(['(index)', 'calendar', 'reservations/:id', 'settings/rooms', 'settings/billing', 'simulators/ota']),
    )
    expect(paths(routes.admin)).toEqual(expect.arrayContaining(['(index)', 'organizations', 'plans', 'billing', 'commissions']))
  })

  it('collects missing groups as empty lists', () => {
    const routes = collectRoutes({ '../features/x/routes.tsx': { routes: { app: [{ path: 'x' }] } } })
    expect(routes).toEqual({ public: [], app: [{ path: 'x' }], admin: [], bare: [] })
  })

  it('nests settings/* routes under the settings layout with relative paths', () => {
    const { main, settings } = splitSettingsRoutes([
      { index: true },
      { path: 'calendar' },
      { path: 'settings/rooms' },
      { path: 'settings/room-types' },
      { path: 'settingsx' },
    ])
    expect(main).toEqual([{ index: true }, { path: 'calendar' }, { path: 'settingsx' }])
    expect(settings).toEqual([{ path: 'rooms' }, { path: 'room-types' }])
  })
})

describe('extension items (widgets, tabs, actions, topbar, commands)', () => {
  const modules = {
    '../features/control/widgets.tsx': {
      widgets: [
        { id: 'alerts', order: 30, size: 'sm', permission: 'control.alerts', Component: () => null },
        { id: 'open-alerts', order: 10, size: 'md', Component: () => null },
      ],
    },
    '../features/revenue/widgets.tsx': {
      widgets: [{ id: 'recommendations', order: 20, size: 'lg', permission: 'revenue.view', Component: () => null }],
    },
    '../features/nothing/widgets.tsx': {},
  }

  it('flattens every module export and sorts by order', () => {
    expect(collectItems(modules, 'widgets').map((w) => w.id)).toEqual(['open-alerts', 'recommendations', 'alerts'])
  })

  it('hides items the user lacks permission for', () => {
    const items = collectItems(modules, 'widgets')
    const can = (code?: string) => !code || code === 'revenue.view'
    expect(visibleItems(items, can).map((w) => w.id)).toEqual(['open-alerts', 'recommendations'])
  })
})

describe('findActiveNav', () => {
  const items = ['/app', '/app/rates', '/app/rates/plans', '/app/reservations', '/app/settings/rooms'].map(
    (path, i): NavItem => ({ id: `n${i}`, section: 'operations', labelKey: 'x:y', icon: Icon, path }),
  )
  const active = (pathname: string) => items.find((item) => item.id === findActiveNav(items, pathname))?.path

  it('picks the most specific item', () => {
    expect(active('/app/rates/plans')).toBe('/app/rates/plans')
    expect(active('/app/rates')).toBe('/app/rates')
  })

  it('keeps the parent active on detail pages', () => {
    expect(active('/app/reservations/9f1c')).toBe('/app/reservations')
  })

  it('matches whole path segments only', () => {
    expect(active('/app/ratesheet')).toBeUndefined()
  })

  it('keeps Today (the /app index) active only on the index itself', () => {
    expect(active('/app')).toBe('/app')
    expect(active('/app/calendar')).toBeUndefined()
  })

  it('returns undefined when nothing matches', () => {
    expect(findActiveNav(items, '/admin')).toBeUndefined()
  })
})
