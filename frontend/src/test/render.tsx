import { QueryClient } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { AppProviders } from '@/app/providers'

/** Fresh client per test: no retries, no cross-test cache. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: Infinity }, mutations: { retry: false } },
  })
}

interface Options extends Omit<RenderOptions, 'wrapper'> {
  /** Initial URL (default `/`). */
  route?: string
  /** Route pattern the element is mounted at (default `*`), e.g. `/app/reservations/:id`. */
  path?: string
  /** Extra routes, e.g. `{ path: '/login', element: <p>login</p> }` to assert redirects. */
  routes?: RouteObject[]
  queryClient?: QueryClient
}

/**
 * Renders `ui` inside the real app providers (TanStack Query, theme, tooltips) and a memory router.
 * Returns the router (assert `router.state.location`), the query client and a userEvent instance.
 */
export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { route = '/', path = '*', routes = [], queryClient = createTestQueryClient(), ...rest } = options
  const router = createMemoryRouter([{ path, element: ui }, ...routes], { initialEntries: [route] })
  const user = userEvent.setup()
  const result = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
    rest,
  )
  return { ...result, router, queryClient, user }
}

/** Renders a whole route tree (e.g. `buildRoutes()`) at `route`. */
export function renderRoutes(routes: RouteObject[], { route = '/', queryClient = createTestQueryClient() } = {}) {
  const router = createMemoryRouter(routes, { initialEntries: [route] })
  const user = userEvent.setup()
  const result = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return { ...result, router, queryClient, user }
}

/**
 * Imports the lazily loaded shells and pages once, so route tests measure behavior and not the
 * first-time module transform. Use in `beforeAll(preloadLazyRoutes, 60_000)`.
 */
export async function preloadLazyRoutes(): Promise<void> {
  await Promise.all([
    import('@/app/layouts/AppLayout'),
    import('@/app/layouts/AdminLayout'),
    import('@/app/layouts/SettingsLayout'),
    import('@/app/pages/SettingsIndex'),
    import('@/app/pages/LoginPage'),
    import('@/components/CommandPalette'),
    import('@/app/shell/ProfileDialog'),
  ])
}
