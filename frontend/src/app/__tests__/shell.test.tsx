import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { buildRoutes } from '@/app/routes'
import { useSession } from '@/lib/session'
import { andinoMembership, auroraMembership, bogotaProperty, makeMe, mockMe } from '@/test/fixtures'
import { preloadLazyRoutes, renderRoutes } from '@/test/render'
import { server } from '@/test/server'

beforeAll(preloadLazyRoutes, 60_000)

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

const mainNav = () => screen.findByRole('navigation', { name: 'Navegación principal' })

describe('AppLayout sidebar', () => {
  it('shows only the sections and pages the role can open', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['housekeeping.view', 'housekeeping.work', 'inventory.view'], 'housekeeping')] }))
    renderRoutes(buildRoutes(), { route: '/app/housekeeping' })

    const nav = await mainNav()
    expect(within(nav).getByRole('link', { name: 'Limpieza' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByText('Operación')).toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: 'Tarifas' })).not.toBeInTheDocument()
    expect(within(nav).queryByText('Ingresos')).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Configuración' })).toHaveAttribute('href', '/app/settings')
  })

  it('marks only the most specific page as current', async () => {
    mockMe(makeMe())
    renderRoutes(buildRoutes(), { route: '/app/rates/plans' })

    const nav = await mainNav()
    expect(within(nav).getByRole('link', { name: 'Planes tarifarios' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Tarifas' })).not.toHaveAttribute('aria-current')
  })
})

describe('AppLayout topbar', () => {
  it('shows the business date of the active property', async () => {
    mockMe(makeMe())
    renderRoutes(buildRoutes(), { route: '/app' })
    expect(await screen.findByText('vie 25 sep')).toBeInTheDocument()
  })

  it('switches property, grouping properties by organization', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(), andinoMembership()] }))
    const { user } = renderRoutes(buildRoutes(), { route: '/app' })

    await user.click(await screen.findByRole('button', { name: /Hotel Casa Aurora/ }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByText('Grupo Andino')).toBeInTheDocument()

    await user.click(within(menu).getByRole('menuitemradio', { name: /Andino Hostel Bogotá/ }))

    expect(await screen.findByRole('button', { name: /Andino Hostel Bogotá/ })).toBeInTheDocument()
    expect(useSession.getState().propertyId).toBe(bogotaProperty.id)
    expect(screen.getByText('sáb 26 sep')).toBeInTheDocument()
  })

  it('opens the command palette with Ctrl+K', async () => {
    mockMe(makeMe())
    const { user } = renderRoutes(buildRoutes(), { route: '/app' })
    await mainNav()

    await user.keyboard('{Control>}k{/Control}')

    expect(await screen.findByRole('dialog', { name: 'Buscar en Housetel' })).toBeInTheDocument()
  })

  it('switches the interface to English and saves it on the profile', async () => {
    mockMe(makeMe())
    let saved: unknown
    server.use(
      http.patch('/api/v1/accounts/me/', async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json(makeMe({ language: 'en' }))
      }),
    )
    const { user } = renderRoutes(buildRoutes(), { route: '/app' })

    await user.click(await screen.findByRole('button', { name: 'Idioma' }))
    await user.click(await screen.findByRole('menuitemradio', { name: 'English' }))

    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    expect(saved).toEqual({ language: 'en' })
  })

  it('logs out from the account menu', async () => {
    mockMe(makeMe())
    server.use(http.post('/api/v1/accounts/auth/logout/', () => new HttpResponse(null, { status: 204 })))
    const { user, router } = renderRoutes(buildRoutes(), { route: '/app' })

    await user.click(await screen.findByRole('button', { name: 'Tu cuenta' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Cerrar sesión' }))

    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    // An explicit logout is not an interrupted visit: the next person starts fresh.
    expect(router.state.location.search).toBe('')
  })
})

describe('AppLayout without properties', () => {
  it('explains what to do and offers to log out', async () => {
    mockMe(makeMe({ memberships: [] }))
    renderRoutes(buildRoutes(), { route: '/app' })

    expect(await screen.findByRole('heading', { name: 'Aún no tienes un hotel asignado' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument()
  })
})

describe('AppLayout on phones', () => {
  const originalMatchMedia = window.matchMedia

  beforeEach(() => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes('max-width: 639px'),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('shows the business date once, under the hotel name, and moves language and theme to the account menu', async () => {
    mockMe(makeMe())
    const { user } = renderRoutes(buildRoutes(), { route: '/app' })

    expect(await screen.findByText('vie 25 sep')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Idioma' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tema' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Tu cuenta' }))
    expect(await screen.findByRole('menuitem', { name: 'Idioma' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Tema' })).toBeInTheDocument()
  })
})
