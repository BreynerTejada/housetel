import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { buildRoutes } from '@/app/routes'
import type { Me } from '@/lib/auth'
import { useSession } from '@/lib/session'
import { makeMe, mockMe } from '@/test/fixtures'
import { preloadLazyRoutes, renderRoutes } from '@/test/render'
import { server } from '@/test/server'

beforeAll(preloadLazyRoutes, 60_000)

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

function answerLogin(me: Me, onBody?: (body: unknown) => void) {
  server.use(
    http.post('/api/v1/accounts/auth/login/', async ({ request }) => {
      onBody?.(await request.json())
      return HttpResponse.json(me)
    }),
  )
}

async function fillAndSubmit(user: ReturnType<typeof renderRoutes>['user'], email: string, password: string) {
  await user.type(await screen.findByLabelText('Correo electrónico'), email)
  await user.type(screen.getByLabelText('Contraseña'), password)
  await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
}

describe('LoginPage', () => {
  it('asks for a valid email and the password before calling the server', async () => {
    mockMe(null)
    const { user } = renderRoutes(buildRoutes(), { route: '/login' })

    await user.click(await screen.findByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findAllByText('Este campo es obligatorio')).toHaveLength(2)

    await user.type(screen.getByLabelText('Correo electrónico'), 'recepcion')
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findByText('Escribe un correo válido')).toBeInTheDocument()
  })

  it('logs in and continues to the page the user wanted', async () => {
    mockMe(null)
    let body: unknown
    answerLogin(makeMe(), (b) => (body = b))
    const { user, router } = renderRoutes(buildRoutes(), { route: '/login?next=%2Fapp%2Fcalendar' })

    await fillAndSubmit(user, 'owner@casaaurora.co', 'housetel123')

    expect(await screen.findByRole('heading', { name: 'Calendario', level: 1 })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/calendar')
    expect(body).toEqual({ email: 'owner@casaaurora.co', password: 'housetel123' })
  })

  it('explains wrong credentials in the UI language', async () => {
    mockMe(null)
    server.use(
      http.post('/api/v1/accounts/auth/login/', () =>
        HttpResponse.json({ detail: 'Credenciales inválidas', code: 'invalid_credentials' }, { status: 400 }),
      ),
    )
    const { user } = renderRoutes(buildRoutes(), { route: '/login' })

    await fillAndSubmit(user, 'owner@casaaurora.co', 'mala-clave')

    expect(await screen.findByRole('alert')).toHaveTextContent('Correo o contraseña incorrectos.')
  })

  it('asks to wait after too many attempts', async () => {
    mockMe(null)
    server.use(
      http.post('/api/v1/accounts/auth/login/', () => HttpResponse.json({ detail: 'x', code: 'throttled' }, { status: 429 })),
    )
    const { user } = renderRoutes(buildRoutes(), { route: '/login' })

    await fillAndSubmit(user, 'owner@casaaurora.co', 'otra')

    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiados intentos. Espera un minuto e inténtalo de nuevo.')
  })

  it('never sends the user outside the app after logging in', async () => {
    mockMe(null)
    answerLogin(makeMe())
    const { user, router } = renderRoutes(buildRoutes(), { route: '/login?next=%2F%2Fevil.example%2Fphish' })

    await fillAndSubmit(user, 'owner@casaaurora.co', 'housetel123')

    expect(await screen.findByRole('heading', { name: 'Hoy', level: 1 })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app')
  })

  it('sends platform admins without a hotel to the platform panel', async () => {
    mockMe(null)
    answerLogin(makeMe({ email: 'admin@housetel.co', is_platform_admin: true, memberships: [] }))
    const { user, router } = renderRoutes(buildRoutes(), { route: '/login' })

    await fillAndSubmit(user, 'admin@housetel.co', 'housetel123')

    expect(await screen.findByRole('heading', { name: 'Resumen', level: 1 })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/admin')
  })

  it('takes signed-in users straight to the app', async () => {
    mockMe(makeMe())
    const { router } = renderRoutes(buildRoutes(), { route: '/login' })

    expect(await screen.findByRole('heading', { name: 'Hoy', level: 1 })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app')
  })

  it('fills the form with a demo account in development', async () => {
    mockMe(null)
    const { user } = renderRoutes(buildRoutes(), { route: '/login' })

    await user.click(await screen.findByRole('button', { name: /Recepción · Casa Aurora/ }))

    expect(screen.getByLabelText('Correo electrónico')).toHaveValue('recepcion@casaaurora.co')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('housetel123')
  })
})
