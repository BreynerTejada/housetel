import { useSession } from './session'

/**
 * Typed API error. The backend normalizes every error to `{detail, code, fields?, ...extra}`
 * (see backend `apps/core/api/exceptions.py`); `data` keeps the whole parsed body.
 * `status` is 0 for network failures (`code = "network_error"`).
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields?: Record<string, string[]>,
    public data?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

type QueryValue = string | number | boolean | undefined | null | string[]
export type Query = Record<string, QueryValue>

export interface RequestOpts {
  /** Query string. Arrays repeat the key; `undefined`, `null` and `''` are skipped. */
  params?: Query
  /** JSON body (ignored when `formData` is given). */
  body?: unknown
  signal?: AbortSignal
  /** Use the public API base (`/api/v1/public`) and never send `X-Property-Id`. */
  public?: boolean
  /** Multipart body; the browser sets the `Content-Type` boundary. */
  formData?: FormData
  /** Set to `false` to handle 401s yourself instead of being sent to `/login` (default `true`). */
  authRedirect?: boolean
  /** `blob` for file downloads (CSV/XLSX/PDF), `text` for plain text. Default `json`. */
  responseType?: 'json' | 'blob' | 'text'
  headers?: Record<string, string>
}

const STAFF_BASE = '/api/v1'
const PUBLIC_BASE = '/api/v1/public'
const CSRF_COOKIE = 'csrftoken'
const CSRF_ENDPOINT = `${STAFF_BASE}/accounts/auth/csrf/`
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])
const PROTECTED_AREA = /^\/(app|admin)(\/|$)/

let onUnauthorized: (url: string) => void = (url) => window.location.assign(url)

/** Replaces what happens when a staff request comes back unauthenticated (tests, router). */
export function setUnauthorizedHandler(handler: (url: string) => void): void {
  onUnauthorized = handler
}

export function getCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=')
    if (key === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

let csrfRequest: Promise<void> | null = null

/** Makes sure the `csrftoken` cookie exists, fetching it at most once for concurrent callers. */
async function ensureCsrfToken(): Promise<string | null> {
  const existing = getCookie(CSRF_COOKIE)
  if (existing) return existing
  csrfRequest ??= fetch(CSRF_ENDPOINT, { credentials: 'include' })
    .then(() => undefined)
    .catch(() => undefined)
    .finally(() => {
      csrfRequest = null
    })
  await csrfRequest
  return getCookie(CSRF_COOKIE)
}

function buildUrl(base: string, path: string, params?: Query): string {
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`
  if (!params) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((item) => search.append(key, item))
    else search.append(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${url}?${qs}` : url
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toApiError(status: number, body: unknown): ApiError {
  if (!isRecord(body)) return new ApiError(status, 'http_error', `HTTP ${status}`)
  const fields = isRecord(body.fields) ? (body.fields as Record<string, string[]>) : undefined
  const code = typeof body.code === 'string' ? body.code : 'http_error'
  const message = typeof body.detail === 'string' && body.detail ? body.detail : `HTTP ${status}`
  return new ApiError(status, code, message, fields, body)
}

function isUnauthenticated(error: ApiError): boolean {
  return (
    error.status === 401 ||
    (error.status === 403 && (error.code === 'not_authenticated' || error.code === 'authentication_failed'))
  )
}

async function readBody(response: Response, responseType: RequestOpts['responseType']): Promise<unknown> {
  if (responseType === 'blob') return response.blob()
  const text = await response.text()
  if (responseType === 'text') return text
  if (!text) return undefined
  const isJson = (response.headers.get('Content-Type') ?? '').includes('json')
  if (!isJson) return text
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

/**
 * The UI language (`<html lang>`, kept in sync by src/lib/i18n), sent as `Accept-Language` so the backend
 * answers errors in the language on screen (plan P1; signed-in users get their profile language, which the UI
 * follows too). Read from the document to avoid importing i18n here (i18n imports this module).
 */
function uiLanguage(): string | null {
  if (typeof document === 'undefined') return null
  const lang = document.documentElement.getAttribute('lang')
  return lang === 'es' || lang === 'en' ? lang : null
}

export async function request<T>(method: string, path: string, opts: RequestOpts = {}): Promise<T> {
  const verb = method.toUpperCase()
  const language = uiLanguage()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(language ? { 'Accept-Language': language } : {}),
    ...opts.headers,
  }
  let body: BodyInit | undefined

  if (opts.formData) {
    body = opts.formData
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }

  if (!opts.public) {
    const propertyId = useSession.getState().propertyId
    if (propertyId) headers['X-Property-Id'] = propertyId
  }

  if (!SAFE_METHODS.has(verb)) {
    const token = await ensureCsrfToken()
    if (token) headers['X-CSRFToken'] = token
  }

  let response: Response
  try {
    response = await fetch(buildUrl(opts.public ? PUBLIC_BASE : STAFF_BASE, path, opts.params), {
      method: verb,
      headers,
      body,
      credentials: 'include',
      signal: opts.signal,
    })
  } catch (error) {
    if (opts.signal?.aborted) throw error
    throw new ApiError(0, 'network_error', error instanceof Error ? error.message : 'Network error')
  }

  if (response.ok) {
    if (response.status === 204 || response.status === 205) return undefined as T
    return (await readBody(response, opts.responseType)) as T
  }

  const error = toApiError(response.status, await readBody(response, 'json'))
  if (isUnauthenticated(error) && !opts.public && opts.authRedirect !== false) {
    const { pathname, search } = window.location
    if (PROTECTED_AREA.test(pathname)) onUnauthorized(`/login?next=${encodeURIComponent(pathname + search)}`)
  }
  throw error
}

type Reader = <T>(path: string, opts?: RequestOpts) => Promise<T>
type Writer = <T>(path: string, body?: unknown, opts?: RequestOpts) => Promise<T>

function client(isPublic: boolean) {
  const read =
    (method: string): Reader =>
    (path, opts) =>
      request(method, path, { ...opts, public: isPublic })
  const write =
    (method: string): Writer =>
    (path, body, opts) =>
      request(method, path, { ...opts, body, public: isPublic })
  return { get: read('GET'), post: write('POST'), put: write('PUT'), patch: write('PATCH'), delete: read('DELETE') }
}

/** Staff API: base `/api/v1`, sends `X-Property-Id` from the session store. */
export const api = client(false)
/** Public API: base `/api/v1/public`, never sends `X-Property-Id`. */
export const publicApi = client(true)
