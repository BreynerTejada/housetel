import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  RequireAuth,
  RequirePlatformAdmin,
  resolveActiveProperty,
  useActiveProperty,
  useLogin,
  useLogout,
  useMe,
} from '@/lib/auth'
import { useCan } from '@/lib/permissions'
import { useSession } from '@/lib/session'
import {
  andinoMembership,
  auroraMembership,
  auroraProperty,
  bogotaProperty,
  makeMe,
  medellinProperty,
  mockMe,
} from '@/test/fixtures'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'

beforeEach(() => {
  useSession.setState({ propertyId: null, loggedOut: false })
  document.cookie = 'csrftoken=t; path=/'
})

function MeProbe() {
  const { data, isPending } = useMe()
  if (isPending) return <p>loading</p>
  return <p>{data ? `signed in as ${data.email}` : 'anonymous'}</p>
}

describe('useMe', () => {
  it('returns null for anonymous visitors instead of failing', async () => {
    mockMe(null)
    renderWithProviders(<MeProbe />)
    expect(await screen.findByText('anonymous')).toBeInTheDocument()
  })

  it('returns the signed-in user', async () => {
    mockMe(makeMe())
    renderWithProviders(<MeProbe />)
    expect(await screen.findByText('signed in as owner@casaaurora.co')).toBeInTheDocument()
  })
})

describe('RequireAuth', () => {
  it('sends anonymous visitors to /login keeping where they were going', async () => {
    mockMe(null)
    const { router } = renderWithProviders(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
      { route: '/app/calendar?view=week', routes: [{ path: '/login', element: <p>login page</p> }] },
    )

    expect(await screen.findByText('login page')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toBe('?next=%2Fapp%2Fcalendar%3Fview%3Dweek')
    expect(screen.queryByText('secret')).not.toBeInTheDocument()
  })

  it('renders the protected content for signed-in users', async () => {
    mockMe(makeMe())
    renderWithProviders(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
    )
    expect(await screen.findByText('secret')).toBeInTheDocument()
  })
})

describe('RequirePlatformAdmin', () => {
  it('sends hotel staff back to the hotel app', async () => {
    mockMe(makeMe({ is_platform_admin: false }))
    const { router } = renderWithProviders(
      <RequirePlatformAdmin>
        <p>platform</p>
      </RequirePlatformAdmin>,
      { route: '/admin', routes: [{ path: '/app', element: <p>hotel app</p> }] },
    )
    expect(await screen.findByText('hotel app')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app')
  })

  it('lets platform admins in', async () => {
    mockMe(makeMe({ is_platform_admin: true, memberships: [] }))
    renderWithProviders(
      <RequirePlatformAdmin>
        <p>platform</p>
      </RequirePlatformAdmin>,
      { route: '/admin' },
    )
    expect(await screen.findByText('platform')).toBeInTheDocument()
  })
})

describe('resolveActiveProperty', () => {
  const me = makeMe({ memberships: [auroraMembership(), andinoMembership(['bookings.view'], 'front_desk')] })

  it('keeps the stored property when the user can still access it', () => {
    const active = resolveActiveProperty(me, bogotaProperty.id)
    expect(active?.property.id).toBe(bogotaProperty.id)
    expect(active?.membership.organization.slug).toBe('grupo-andino')
  })

  it('falls back to the first property when the stored one is not accessible', () => {
    expect(resolveActiveProperty(me, 'someone-elses-property')?.property.id).toBe(auroraProperty.id)
    expect(resolveActiveProperty(me, null)?.property.id).toBe(auroraProperty.id)
  })

  it('returns null when the user has no properties', () => {
    expect(resolveActiveProperty(makeMe({ memberships: [] }), null)).toBeNull()
  })
})

function ActiveProbe() {
  const { property, setProperty } = useActiveProperty()
  const canCheckIn = useCan('bookings.checkin')
  const canView = useCan('bookings.view')
  const canAlways = useCan()
  return (
    <div>
      <p>property: {property?.name ?? 'none'}</p>
      <p>checkin: {String(canCheckIn)}</p>
      <p>view: {String(canView)}</p>
      <p>no permission needed: {String(canAlways)}</p>
      <button onClick={() => setProperty(medellinProperty.id)}>switch</button>
    </div>
  )
}

describe('useActiveProperty and useCan', () => {
  it('writes the resolved property to the session store and checks permissions against its membership', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['*']), andinoMembership(['bookings.view'], 'front_desk')] }))
    const { user } = renderWithProviders(<ActiveProbe />)

    expect(await screen.findByText('property: Hotel Casa Aurora')).toBeInTheDocument()
    await waitFor(() => expect(useSession.getState().propertyId).toBe(auroraProperty.id))
    expect(screen.getByText('checkin: true')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'switch' }))

    expect(await screen.findByText('property: Andino Medellín')).toBeInTheDocument()
    expect(useSession.getState().propertyId).toBe(medellinProperty.id)
    expect(screen.getByText('checkin: false')).toBeInTheDocument()
    expect(screen.getByText('view: true')).toBeInTheDocument()
    expect(screen.getByText('no permission needed: true')).toBeInTheDocument()
  })
})

function LoginLogoutProbe() {
  const me = useMe()
  const login = useLogin()
  const logout = useLogout()
  return (
    <div>
      <p>{me.data ? me.data.email : 'anonymous'}</p>
      <button onClick={() => login.mutate({ email: 'Owner@CasaAurora.co', password: 'housetel123' })}>login</button>
      <button onClick={() => logout.mutate()}>logout</button>
    </div>
  )
}

describe('useLogin and useLogout', () => {
  it('stores the user returned by login and forgets everything on logout', async () => {
    mockMe(null)
    let credentials: unknown
    server.use(
      http.post('/api/v1/accounts/auth/login/', async ({ request }) => {
        credentials = await request.json()
        return HttpResponse.json(makeMe())
      }),
      http.post('/api/v1/accounts/auth/logout/', () => new HttpResponse(null, { status: 204 })),
    )
    const { user, queryClient } = renderWithProviders(<LoginLogoutProbe />)
    expect(await screen.findByText('anonymous')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'login' }))

    expect(await screen.findByText('owner@casaaurora.co')).toBeInTheDocument()
    expect(credentials).toEqual({ email: 'Owner@CasaAurora.co', password: 'housetel123' })

    useSession.setState({ propertyId: auroraProperty.id })
    queryClient.setQueryData(['bookings', 'reservations'], { count: 3 })
    await user.click(screen.getByRole('button', { name: 'logout' }))

    expect(await screen.findByText('anonymous')).toBeInTheDocument()
    expect(queryClient.getQueryData(['bookings', 'reservations'])).toBeUndefined()
    expect(useSession.getState().propertyId).toBeNull()
  })
})
