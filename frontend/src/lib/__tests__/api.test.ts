import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, publicApi, setUnauthorizedHandler } from '@/lib/api'
import { useSession } from '@/lib/session'
import { server } from '@/test/server'

function clearCookies() {
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0]?.trim()
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
  }
}

beforeEach(() => {
  clearCookies()
  useSession.setState({ propertyId: null })
  window.history.pushState({}, '', '/')
})

afterEach(() => {
  setUnauthorizedHandler((url) => window.location.assign(url))
})

describe('staff api', () => {
  it('prefixes /api/v1 and sends the active property header', async () => {
    useSession.setState({ propertyId: 'prop-123' })
    let seen: Request | undefined
    server.use(
      http.get('/api/v1/bookings/reservations/', ({ request }) => {
        seen = request
        return HttpResponse.json({ count: 0, results: [] })
      }),
    )

    const data = await api.get<{ count: number }>('/bookings/reservations/')

    expect(data.count).toBe(0)
    expect(seen?.headers.get('X-Property-Id')).toBe('prop-123')
  })

  it('omits the property header when no property is selected', async () => {
    let seen: Request | undefined
    server.use(
      http.get('/api/v1/accounts/me/', ({ request }) => {
        seen = request
        return HttpResponse.json({})
      }),
    )

    await api.get('/accounts/me/')

    expect(seen?.headers.has('X-Property-Id')).toBe(false)
  })

  it('serializes query params, repeating arrays and skipping empty values', async () => {
    let url: URL | undefined
    server.use(
      http.get('/api/v1/bookings/reservations/', ({ request }) => {
        url = new URL(request.url)
        return HttpResponse.json({})
      }),
    )

    await api.get('/bookings/reservations/', {
      params: { status: ['confirmed', 'tentative'], page: 2, unassigned: true, q: undefined, source: null },
    })

    expect(url?.searchParams.getAll('status')).toEqual(['confirmed', 'tentative'])
    expect(url?.searchParams.get('page')).toBe('2')
    expect(url?.searchParams.get('unassigned')).toBe('true')
    expect(url?.searchParams.has('q')).toBe(false)
    expect(url?.searchParams.has('source')).toBe(false)
  })
})

describe('public api', () => {
  it('prefixes /api/v1/public and never sends the property header', async () => {
    useSession.setState({ propertyId: 'prop-123' })
    let seen: Request | undefined
    server.use(
      http.get('/api/v1/public/core/health/', ({ request }) => {
        seen = request
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    const data = await publicApi.get<{ status: string }>('/core/health/')

    expect(data.status).toBe('ok')
    expect(seen?.headers.has('X-Property-Id')).toBe(false)
  })
})

describe('CSRF', () => {
  it('sends the csrftoken cookie as X-CSRFToken on unsafe methods', async () => {
    document.cookie = 'csrftoken=cookie-token; path=/'
    let seen: Request | undefined
    server.use(
      http.post('/api/v1/bookings/reservations/', ({ request }) => {
        seen = request
        return HttpResponse.json({ id: 'r1' }, { status: 201 })
      }),
    )

    await api.post('/bookings/reservations/', { adults: 2 })

    expect(seen?.headers.get('X-CSRFToken')).toBe('cookie-token')
    expect(seen?.headers.get('Content-Type')).toContain('application/json')
    expect(await seen?.json()).toEqual({ adults: 2 })
  })

  it('fetches the csrf cookie once when it is missing, even for concurrent requests', async () => {
    let csrfCalls = 0
    const tokens: (string | null)[] = []
    server.use(
      http.get('/api/v1/accounts/auth/csrf/', () => {
        csrfCalls += 1
        // The browser would store the Set-Cookie header; emulate the cookie jar.
        document.cookie = 'csrftoken=fresh-token; path=/'
        return new HttpResponse(null, { status: 204 })
      }),
      http.post('/api/v1/accounts/auth/logout/', ({ request }) => {
        tokens.push(request.headers.get('X-CSRFToken'))
        return new HttpResponse(null, { status: 204 })
      }),
    )

    await Promise.all([api.post('/accounts/auth/logout/'), api.post('/accounts/auth/logout/')])

    expect(csrfCalls).toBe(1)
    expect(tokens).toEqual(['fresh-token', 'fresh-token'])
  })

  it('does not request a token for safe methods', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => HttpResponse.json({ id: 'u1' })))
    // An unhandled request to the csrf endpoint would fail the test (onUnhandledRequest: 'error').
    await expect(api.get('/accounts/me/')).resolves.toEqual({ id: 'u1' })
  })
})

describe('responses and errors', () => {
  it('returns undefined for 204 No Content', async () => {
    document.cookie = 'csrftoken=t; path=/'
    server.use(http.delete('/api/v1/rates/extras/e1/', () => new HttpResponse(null, { status: 204 })))

    await expect(api.delete('/rates/extras/e1/')).resolves.toBeUndefined()
  })

  it('parses {detail, code, fields} into an ApiError', async () => {
    document.cookie = 'csrftoken=t; path=/'
    server.use(
      http.post('/api/v1/bookings/reservations/', () =>
        HttpResponse.json(
          { detail: 'Datos inválidos', code: 'validation_error', fields: { adults: ['Requerido'] }, hint: 'x' },
          { status: 400 },
        ),
      ),
    )

    const error = await api.post('/bookings/reservations/', {}).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.status).toBe(400)
    expect(apiError.code).toBe('validation_error')
    expect(apiError.message).toBe('Datos inválidos')
    expect(apiError.fields).toEqual({ adults: ['Requerido'] })
    expect(apiError.data?.hint).toBe('x')
  })

  it('maps a non-JSON error page to an http_error', async () => {
    server.use(
      http.get('/api/v1/reports/performance/', () =>
        new HttpResponse('<html>Bad gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }),
      ),
    )

    const error = (await api.get('/reports/performance/').catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.code).toBe('http_error')
  })

  it('maps a network failure to a network_error', async () => {
    server.use(http.get('/api/v1/reports/performance/', () => HttpResponse.error()))

    const error = (await api.get('/reports/performance/').catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(0)
    expect(error.code).toBe('network_error')
  })

  it('sends FormData as multipart without forcing a JSON content type', async () => {
    document.cookie = 'csrftoken=t; path=/'
    let contentType: string | null = null
    let caption: FormDataEntryValue | null = null
    server.use(
      http.post('/api/v1/inventory/room-types/rt1/photos/', async ({ request }) => {
        contentType = request.headers.get('Content-Type')
        caption = (await request.formData()).get('caption')
        return HttpResponse.json({ id: 'ph1' }, { status: 201 })
      }),
    )
    const form = new FormData()
    form.append('caption', 'Vista al mar')

    await api.post('/inventory/room-types/rt1/photos/', undefined, { formData: form })

    expect(contentType).toMatch(/^multipart\/form-data; boundary=/)
    expect(caption).toBe('Vista al mar')
  })

  it('returns the raw body as a Blob for downloads, keeping the property header', async () => {
    useSession.setState({ propertyId: 'prop-9' })
    let seen: Request | undefined
    server.use(
      http.get('/api/v1/reports/performance/', ({ request }) => {
        seen = request
        return new HttpResponse('fecha;ocupacion\n2026-10-12;81', { headers: { 'Content-Type': 'text/csv' } })
      }),
    )

    const file = await api.get<Blob>('/reports/performance/', { params: { format: 'csv' }, responseType: 'blob' })

    expect(file.type).toContain('text/csv')
    expect(await file.text()).toBe('fecha;ocupacion\n2026-10-12;81')
    expect(seen?.headers.get('X-Property-Id')).toBe('prop-9')
  })
})

describe('unauthenticated responses', () => {
  it('sends staff users to /login with the current location on 401 inside /app', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    window.history.pushState({}, '', '/app/calendar?view=week')
    server.use(http.get('/api/v1/bookings/calendar/', () => HttpResponse.json({ detail: 'No autenticado' }, { status: 401 })))

    await expect(api.get('/bookings/calendar/')).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledWith('/login?next=%2Fapp%2Fcalendar%3Fview%3Dweek')
  })

  it("treats DRF's 403 not_authenticated like a 401", async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    window.history.pushState({}, '', '/admin/plans')
    server.use(
      http.get('/api/v1/saas/admin/plans/', () =>
        HttpResponse.json({ detail: 'No autenticado', code: 'not_authenticated' }, { status: 403 }),
      ),
    )

    await expect(api.get('/saas/admin/plans/')).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledWith('/login?next=%2Fadmin%2Fplans')
  })

  it('does not redirect on public pages, on permission errors, or when disabled per request', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    server.use(
      http.get('/api/v1/accounts/me/', () => HttpResponse.json({ detail: 'x', code: 'not_authenticated' }, { status: 403 })),
      http.get('/api/v1/finance/folios/', () =>
        HttpResponse.json({ detail: 'Sin permiso', code: 'permission_denied' }, { status: 403 }),
      ),
    )

    window.history.pushState({}, '', '/hotel/casa-aurora')
    await api.get('/accounts/me/').catch(() => undefined)
    window.history.pushState({}, '', '/app')
    await api.get('/finance/folios/').catch(() => undefined)
    await api.get('/accounts/me/', { authRedirect: false }).catch(() => undefined)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
