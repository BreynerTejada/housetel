import { useMutation, useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { useCallback, useEffect, useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, useLocation } from 'react-router'
import { api, ApiError } from './api'
import { matchPermission } from './permissions'
import { useSession } from './session'

// ---- Types: exact shape of GET /api/v1/accounts/me/ (spec §3) ---------------------------------

export type OrganizationStatus = 'trial' | 'active' | 'past_due' | 'suspended' | 'cancelled'
export type PropertyType = 'hotel' | 'hostel' | 'boutique' | 'aparthotel' | 'glamping'

export interface OrganizationSummary {
  id: string
  name: string
  slug: string
  status: OrganizationStatus
}

export interface RoleSummary {
  id: string
  name: string
  code: string
}

export interface PropertySummary {
  id: string
  name: string
  slug: string
  property_type: PropertyType
  timezone: string
  currency: string
  /** `YYYY-MM-DD`; advances with the night audit. */
  business_date: string
}

export interface Membership {
  organization: OrganizationSummary
  role: RoleSummary
  /** Codes or fnmatch patterns exactly as stored on the role (`bookings.*`, `*`). */
  permissions: string[]
  properties: PropertySummary[]
}

export interface Me {
  id: string
  email: string
  full_name: string
  language: 'es' | 'en'
  /** Not in the spec §3 list, but `PATCH /accounts/me/` writes it, so the backend returns it too (A3). */
  phone: string
  is_platform_admin: boolean
  memberships: Membership[]
}

export interface PropertyAccess {
  property: PropertySummary
  membership: Membership
}

export const ME_QUERY_KEY = ['me'] as const

const notMe = (query: Query) => query.queryKey[0] !== ME_QUERY_KEY[0]

function isUnauthenticated(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 401 ||
      (error.status === 403 && (error.code === 'not_authenticated' || error.code === 'authentication_failed')))
  )
}

/** Current user, or `null` for anonymous visitors (never redirects by itself). */
export async function fetchMe(): Promise<Me | null> {
  try {
    return await api.get<Me>('/accounts/me/', { authRedirect: false })
  } catch (error) {
    if (isUnauthenticated(error)) return null
    throw error
  }
}

export function useMe() {
  return useQuery({ queryKey: ME_QUERY_KEY, queryFn: fetchMe, staleTime: 5 * 60_000 })
}

export interface Credentials {
  email: string
  password: string
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentials: Credentials) =>
      api.post<Me>('/accounts/auth/login/', credentials, { authRedirect: false }),
    onSuccess: (me) => {
      useSession.getState().setLoggedOut(false)
      queryClient.setQueryData(ME_QUERY_KEY, me)
    },
  })
}

/**
 * Ends the session and forgets every cached answer and the active property. The route guards then
 * send the user to a clean `/login` (no `?next=`: the next person at the front desk starts fresh).
 */
export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<void>('/accounts/auth/logout/', undefined, { authRedirect: false }),
    onSettled: async () => {
      await queryClient.cancelQueries({ predicate: notMe })
      useSession.getState().setLoggedOut(true)
      queryClient.removeQueries({ predicate: notMe })
      queryClient.setQueryData(ME_QUERY_KEY, null)
      useSession.getState().setPropertyId(null)
    },
  })
}

// ---- Active property --------------------------------------------------------------------------

export function listPropertyAccess(me: Me | null | undefined): PropertyAccess[] {
  return me?.memberships.flatMap((membership) => membership.properties.map((property) => ({ property, membership }))) ?? []
}

/** The stored property when the user can still access it; otherwise their first property. */
export function resolveActiveProperty(me: Me | null | undefined, storedId: string | null): PropertyAccess | null {
  const all = listPropertyAccess(me)
  return all.find((item) => item.property.id === storedId) ?? all[0] ?? null
}

export function useActiveProperty() {
  const { data: me } = useMe()
  const storedId = useSession((state) => state.propertyId)
  const setStoredId = useSession((state) => state.setPropertyId)
  const queryClient = useQueryClient()

  const properties = useMemo(() => listPropertyAccess(me), [me])
  const active = useMemo(() => resolveActiveProperty(me, storedId), [me, storedId])

  useEffect(() => {
    if (active && active.property.id !== storedId) setStoredId(active.property.id)
  }, [active, storedId, setStoredId])

  /** Switches property: data of the previous one is dropped so nothing leaks across hotels. */
  const setProperty = useCallback(
    (id: string) => {
      if (id === useSession.getState().propertyId) return
      setStoredId(id)
      void queryClient.cancelQueries({ predicate: notMe })
      queryClient.removeQueries({ predicate: notMe })
    },
    [queryClient, setStoredId],
  )

  return {
    property: active?.property ?? null,
    membership: active?.membership ?? null,
    properties,
    setProperty,
    /** True once `X-Property-Id` (session store) matches the resolved property. */
    synced: active !== null && active.property.id === storedId,
  }
}

export function useActiveMembership(): Membership | null {
  return useActiveProperty().membership
}

/** Where a user lands after logging in when nothing else was requested. */
export function homeFor(me: Me): string {
  const withProperties = me.memberships.filter((membership) => membership.properties.length > 0)
  if (!withProperties.length && me.is_platform_admin) return '/admin'
  // A suspended organization only keeps billing (the rest of the staff API answers 402): whoever can pay lands
  // there instead of on a Today panel full of errors.
  const suspended =
    withProperties.length > 0 && withProperties.every((membership) => membership.organization.status === 'suspended')
  if (suspended && withProperties.some((membership) => matchPermission(membership.permissions, 'saas.billing_view'))) {
    return '/app/settings/billing'
  }
  return '/app'
}

/** A `?next=` target only if it stays inside this app (no `//host`, no loops back to /login). */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null
  if (next === '/login' || next.startsWith('/login?') || next.startsWith('/login/')) return null
  return next
}

// ---- Route guards -----------------------------------------------------------------------------

function FullPageStatus({ error, onRetry }: { error?: boolean; onRetry?: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="grid min-h-dvh place-items-center bg-bg p-6 text-sm text-muted" role={error ? 'alert' : 'status'}>
      {error ? (
        <div className="max-w-sm text-center">
          <p className="font-semibold text-fg">{t('states.error')}</p>
          <p className="mt-1">{t('errors.network')}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-md border border-border bg-surface px-3 py-1.5 font-semibold text-fg hover:bg-surface-2"
          >
            {t('actions.retry')}
          </button>
        </div>
      ) : (
        <span className="inline-flex items-center gap-2">
          <LoaderCircle aria-hidden className="size-4 animate-spin text-accent" />
          {t('states.loading')}
        </span>
      )}
    </div>
  )
}

/** `/login?next=<here>` for interrupted visits (expired session); a plain `/login` after logging out. */
function useLoginRedirect(): string {
  const { pathname, search } = useLocation()
  const loggedOut = useSession((state) => state.loggedOut)
  return loggedOut ? '/login' : `/login?next=${encodeURIComponent(pathname + search)}`
}

/** Staff-only area: anonymous visitors go to `/login?next=<where they were going>`. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { data: me, isPending, isError, refetch } = useMe()
  const loginRedirect = useLoginRedirect()
  if (isPending) return <FullPageStatus />
  if (isError) return <FullPageStatus error onRetry={() => void refetch()} />
  if (!me) return <Navigate to={loginRedirect} replace />
  return <>{children ?? <Outlet />}</>
}

/** Platform super-admin area: other signed-in users are sent to the hotel app. */
export function RequirePlatformAdmin({ children }: { children?: ReactNode }) {
  const { data: me, isPending, isError, refetch } = useMe()
  const loginRedirect = useLoginRedirect()
  if (isPending) return <FullPageStatus />
  if (isError) return <FullPageStatus error onRetry={() => void refetch()} />
  if (!me) return <Navigate to={loginRedirect} replace />
  if (!me.is_platform_admin) return <Navigate to="/app" replace />
  return <>{children ?? <Outlet />}</>
}
