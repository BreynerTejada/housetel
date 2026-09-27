import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { matchRoutes } from 'react-router'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { getNav } from '@/app/extensions'
import { buildRoutes } from '@/app/routes'
import { useSession } from '@/lib/session'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { preloadLazyRoutes, renderRoutes } from '@/test/render'
import { server } from '@/test/server'

beforeAll(preloadLazyRoutes, 60_000)

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
})

describe('route tree', () => {
  it('has a real page for every nav item (no dead links)', () => {
    const routes = buildRoutes()
    for (const item of getNav()) {
      const leaf = matchRoutes(routes, item.path)?.at(-1)?.route
      expect({ path: item.path, leaf: leaf?.path ?? (leaf?.index ? '(index)' : undefined) }).not.toEqual({
        path: item.path,
        leaf: '*',
      })
      expect(leaf).toBeDefined()
    }
  })
})

describe('staff area', () => {
  it('sends anonymous visitors to the login page, remembering the destination', async () => {
    mockMe(null)
    const { router } = renderRoutes(buildRoutes(), { route: '/app/calendar' })

    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toBe('?next=%2Fapp%2Fcalendar')
  })

  it('nests settings pages in the settings layout', async () => {
    mockMe(makeMe())
    // The rooms page is real since phase B: an empty inventory is enough for the layout.
    server.use(
      http.get('/api/v1/inventory/rooms/', () => HttpResponse.json([])),
      http.get('/api/v1/inventory/room-types/', () => HttpResponse.json([])),
      http.get('/api/v1/inventory/custom-fields/', () => HttpResponse.json([])),
    )
    renderRoutes(buildRoutes(), { route: '/app/settings/rooms' })

    expect(await screen.findByRole('heading', { name: 'Habitaciones', level: 1 })).toBeInTheDocument()
    const settingsNav = screen.getByRole('navigation', { name: 'Secciones de configuración' })
    expect(within(settingsNav).getByRole('link', { name: 'Habitaciones' })).toHaveAttribute('aria-current', 'page')
    expect(within(settingsNav).getByRole('link', { name: 'Impuestos' })).toBeInTheDocument()
  })

  it('lists the settings sections the user can open on the settings index', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['inventory.view', 'rates.manage'], 'custom')] }))
    renderRoutes(buildRoutes(), { route: '/app/settings' })

    const main = await screen.findByRole('main')
    expect(await within(main).findByRole('heading', { name: 'Configuración', level: 1 })).toBeInTheDocument()
    expect(within(main).getByRole('link', { name: /Habitaciones/ })).toHaveAttribute('href', '/app/settings/rooms')
    expect(within(main).getByText('Desayuno, parqueadero, traslados y otros servicios que se cobran aparte.')).toBeInTheDocument()
    expect(within(main).queryByRole('link', { name: /Usuarios/ })).not.toBeInTheDocument()
  })

  it('shows not-found inside the shell for unknown staff pages', async () => {
    mockMe(makeMe())
    renderRoutes(buildRoutes(), { route: '/app/no-existe' })

    expect(await screen.findByRole('heading', { name: 'No encontramos esta página' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
  })
})

describe('platform area', () => {
  it('sends hotel staff back to the hotel app', async () => {
    mockMe(makeMe())
    const { router } = renderRoutes(buildRoutes(), { route: '/admin/plans' })

    expect(await screen.findByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app')
  })

  it('opens the platform panel for super admins', async () => {
    mockMe(makeMe({ email: 'admin@housetel.co', is_platform_admin: true, memberships: [] }))
    renderRoutes(buildRoutes(), { route: '/admin/plans' })

    expect(await screen.findByText('Panel de plataforma')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Planes', level: 1 })).toBeInTheDocument()
    const adminNav = screen.getByRole('navigation', { name: 'Navegación de la plataforma' })
    expect(within(adminNav).getByRole('link', { name: 'Organizaciones' })).toHaveAttribute('href', '/admin/organizations')
  })
})

describe('public area', () => {
  it('shows the marketplace home with the Housetel header at /', async () => {
    mockMe(null)
    renderRoutes(buildRoutes(), { route: '/' })

    expect(await screen.findByRole('heading', { name: 'Reserva directo con el hotel.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Para hoteles' })).toHaveAttribute('href', '/signup')
    expect(screen.getByRole('link', { name: 'Ingresar' })).toHaveAttribute('href', '/login')
  })

  it('hides the Housetel header on hotel-branded pages', async () => {
    mockMe(null)
    renderRoutes(buildRoutes(), { route: '/h/casa-aurora' })

    expect(await screen.findByRole('heading', { name: 'Reservas directas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Para hoteles' })).not.toBeInTheDocument()
  })

  it('shows not-found for unknown public pages', async () => {
    mockMe(null)
    renderRoutes(buildRoutes(), { route: '/no-existe' })
    expect(await screen.findByRole('heading', { name: 'No encontramos esta página' })).toBeInTheDocument()
  })
})
