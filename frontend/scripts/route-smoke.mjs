// Route smoke in a private headless Chrome (own profile and port; never the shared browser): opens every route
// of the SPA (plan §E / spec §7.1) as the right user and reports uncaught exceptions, console errors, API
// responses >= 400, the Vite error overlay and horizontal overflow (page wider than the viewport).
//
//   node frontend/scripts/route-smoke.mjs                 # 1440 px
//   WIDTH=375 node frontend/scripts/route-smoke.mjs       # phone width
//   ONLY=/app/revenue,/app/inbox node frontend/scripts/route-smoke.mjs   # prefixes; `/app$` = exactly /app
//
// Needs the stack up with the demo seeded (`make up`, `make seed`), Node >= 22 (global fetch/WebSocket) and
// Chrome (`CHROME=/path/to/chrome`, default google-chrome-stable). Read-only: it only navigates.
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const BASE = process.env.BASE || 'http://localhost:5173'
const CHROME = process.env.CHROME || 'google-chrome-stable'
const PORT = Number(process.env.PORT || 9557)
const WIDTH = Number(process.env.WIDTH || 1440)
const ONLY = (process.env.ONLY || '').split(',').filter(Boolean)
const PASSWORD = 'housetel123'

const profile = mkdtempSync(join(tmpdir(), 'housetel-route-smoke-'))
const chrome = spawn(
  CHROME,
  ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', `--user-data-dir=${profile}`,
    `--remote-debugging-port=${PORT}`, `--window-size=${WIDTH},900`, 'about:blank'],
  { stdio: 'ignore' },
)
const cleanup = () => {
  chrome.kill()
  try {
    rmSync(profile, { recursive: true, force: true })
  } catch {
    /* chrome may still hold files */
  }
}

async function pageTarget() {
  for (let i = 0; i < 75; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      const page = list.find((t) => t.type === 'page')
      if (page) return page
    } catch {
      /* not up yet */
    }
    await sleep(200)
  }
  throw new Error('Chrome did not start (set CHROME=/path/to/chrome)')
}

const target = await pageTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }))
let seq = 0
const pending = new Map()
let problems = []
const inflight = new Map()
let lastNetwork = Date.now()
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data)
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg)
    pending.delete(msg.id)
    return
  }
  const p = msg.params
  switch (msg.method) {
    case 'Runtime.exceptionThrown':
      problems.push(`exception: ${(p.exceptionDetails.exception?.description ?? p.exceptionDetails.text).slice(0, 300)}`)
      break
    case 'Runtime.consoleAPICalled':
      if (p.type === 'error' || p.type === 'assert') {
        problems.push(`console.${p.type}: ${p.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 300)}`)
      }
      break
    case 'Network.requestWillBeSent':
      inflight.set(p.requestId, p.request.url)
      lastNetwork = Date.now()
      break
    case 'Network.responseReceived': {
      const { url, status } = p.response
      if (status >= 400 && url.includes('/api/')) problems.push(`HTTP ${status} ${url.replace(BASE, '')}`)
      break
    }
    case 'Network.loadingFinished':
    case 'Network.loadingFailed':
      if (msg.method === 'Network.loadingFailed' && !p.canceled && inflight.get(p.requestId)?.includes('/api/')) {
        problems.push(`request failed: ${inflight.get(p.requestId).replace(BASE, '')} (${p.errorText})`)
      }
      inflight.delete(p.requestId)
      lastNetwork = Date.now()
      break
  }
})

function send(method, params = {}) {
  const id = ++seq
  ws.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve) => pending.set(id, resolve))
}

async function evaluate(expression) {
  const res = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (res.result?.exceptionDetails) throw new Error(JSON.stringify(res.result.exceptionDetails).slice(0, 400))
  return res.result?.result?.value
}

/** Navigate and wait until the network is quiet (polling pages never go fully idle: capped). */
async function open(path) {
  inflight.clear()
  await send('Page.navigate', { url: BASE + path })
  const started = Date.now()
  await sleep(1200)
  while (Date.now() - started < 12000) {
    if (inflight.size === 0 && Date.now() - lastNetwork > 900) break
    await sleep(150)
  }
  await sleep(400)
}

async function api(path, init = {}) {
  return evaluate(`(async () => {
    const token = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))?.split('=')[1]
    const pid = ${JSON.stringify(init.property ?? null)}
    const headers = { 'Content-Type': 'application/json', ...(token ? { 'X-CSRFToken': token } : {}), ...(pid ? { 'X-Property-Id': pid } : {}) }
    const res = await fetch(${JSON.stringify(path)}, { method: ${JSON.stringify(init.method ?? 'GET')}, credentials: 'include', headers,
      body: ${init.body ? JSON.stringify(JSON.stringify(init.body)) : 'undefined'} })
    const text = await res.text()
    try { return { status: res.status, data: JSON.parse(text) } } catch { return { status: res.status, data: text } }
  })()`)
}

async function login(email) {
  await send('Network.clearBrowserCookies')
  await open('/login')
  await api('/api/v1/accounts/auth/csrf/')
  const res = await api('/api/v1/accounts/auth/login/', { method: 'POST', body: { email, password: PASSWORD } })
  if (res.status !== 200) throw new Error(`login ${email}: ${res.status} ${JSON.stringify(res.data).slice(0, 200)}`)
  return res.data
}

const rows = []
async function visit(path, { label = path, expectHttp = [], heading = true } = {}) {
  if (ONLY.length && !ONLY.some((only) => (only.endsWith('$') ? path === only.slice(0, -1) : path.startsWith(only)))) {
    return false
  }
  problems = []
  await open(path)
  const overlay = await evaluate(`Boolean(document.querySelector('vite-error-overlay'))`)
  const h1 = await evaluate(`(document.querySelector('h1')?.textContent ?? '').trim().slice(0, 60)`)
  const overflow = await evaluate(
    `document.documentElement.scrollWidth > window.innerWidth + 1 ? document.documentElement.scrollWidth : 0`,
  )
  const found = problems.filter((p) => !expectHttp.some((code) => p.startsWith(`HTTP ${code} `)))
  if (overlay) found.push('vite error overlay')
  if (overflow) found.push(`horizontal overflow: ${overflow}px > ${WIDTH}px`)
  if (heading && !h1) found.push('no <h1>')
  rows.push({ label, h1, problems: found })
  console.log(`${found.length ? 'ERR' : 'ok '} ${label.padEnd(44)} ${h1}`)
  for (const problem of found) console.log(`      ${problem}`)
  return true
}

await send('Runtime.enable')
await send('Network.enable')
await send('Page.enable')
await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: 900, deviceScaleFactor: 1, mobile: WIDTH < 600 })

try {
  // ---- Staff (owner of Casa Aurora): every /app route ------------------------------------------------------
  const me = await login('owner@casaaurora.co')
  const prop = me.memberships[0].properties[0]
  const pid = prop.id
  const today = prop.business_date
  const arrivals = (await api('/api/v1/frontdesk/today/', { property: pid })).data
  const reservationId =
    arrivals.arrivals?.[0]?.reservation_id ??
    (await api('/api/v1/bookings/reservations/?page_size=1', { property: pid })).data.results[0].id
  const guestId = (await api('/api/v1/guests/guests/?page_size=1', { property: pid })).data.results[0].id
  const roomTypes = (await api('/api/v1/inventory/room-types/', { property: pid })).data
  const rooms = (await api('/api/v1/inventory/rooms/', { property: pid })).data
  const roomTypeId = (roomTypes.results ?? roomTypes)[0].id
  const roomId = (rooms.results ?? rooms)[0].id
  const link = (await api(`/api/v1/guestportal/reservations/${reservationId}/link/`, { property: pid })).data
  const portalToken = link.url.replace(/\/$/, '').split('/').pop()

  const appRoutes = [
    '/app', '/app/calendar', '/app/reservations', '/app/reservations/new', `/app/reservations/${reservationId}`,
    `/app/reservations/${reservationId}?tab=folio`, '/app/night-audit', '/app/guests', `/app/guests/${guestId}`,
    '/app/housekeeping', '/app/housekeeping/mine', '/app/maintenance', '/app/rates', '/app/rates/plans',
    '/app/rates/promos', '/app/revenue', '/app/channels', '/app/simulators/ota', '/app/inbox',
    '/app/simulators/whatsapp', '/app/cashier', '/app/compliance', '/app/reports', '/app/reports/performance',
    '/app/reports/arrivals', '/app/reports/taxes', '/app/alerts', '/app/onboarding', '/app/getting-started',
    '/app/settings/property', '/app/settings/room-types', `/app/settings/room-types/${roomTypeId}`,
    '/app/settings/rooms', `/app/settings/rooms/${roomId}`, '/app/settings/custom-fields', '/app/settings/taxes',
    '/app/settings/policies', '/app/settings/extras', '/app/settings/booking-engine', '/app/settings/users',
    '/app/settings/roles', '/app/settings/integrations', '/app/settings/automations', '/app/settings/audit',
    '/app/settings/billing', '/app/settings/messaging', '/app/settings/compliance', '/app/settings/housekeeping',
    '/app/settings/guest-portal', '/app/settings/chatbot', '/app/settings/ai',
  ] // prettier-ignore
  console.log(`\n== staff · owner@casaaurora.co · ${prop.name} · ${today} · ${WIDTH}px`)
  for (const path of appRoutes) await visit(path)

  // ---- Other roles: where each one lands and its own pages -------------------------------------------------
  for (const [email, paths] of [
    ['limpieza@casaaurora.co', ['/app', '/app/housekeeping/mine']],
    ['mantenimiento@casaaurora.co', ['/app', '/app/maintenance']],
    ['recepcion@casaaurora.co', ['/app', '/app/reservations', '/app/calendar', '/app/inbox']],
    ['contabilidad@casaaurora.co', ['/app', '/app/reports', '/app/compliance', '/app/cashier']],
  ]) {
    await login(email)
    console.log(`\n== ${email}`)
    for (const path of paths) {
      if (!(await visit(path, { label: `${path} (${email.split('@')[0]})` }))) continue
      const landed = await evaluate('location.pathname')
      if (landed !== path) console.log(`      → lands on ${landed}`)
    }
  }

  // ---- Platform admin ----------------------------------------------------------------------------------------
  await login('admin@housetel.co')
  const orgs = (await api('/api/v1/saas/admin/organizations/')).data
  console.log('\n== super-admin · admin@housetel.co')
  for (const path of ['/admin', '/admin/organizations', `/admin/organizations/${orgs.results[0].id}`, '/admin/plans',
    '/admin/billing', '/admin/commissions']) await visit(path) // prettier-ignore

  // ---- Public (no session) -----------------------------------------------------------------------------------
  await send('Network.clearBrowserCookies')
  const plus = (days) => new Date(Date.parse(`${today}T12:00:00Z`) + days * 864e5).toISOString().slice(0, 10)
  const stay = `checkin=${plus(22)}&checkout=${plus(24)}&adults=2`
  console.log('\n== public (no session)')
  const publicRoutes = [
    '/', `/search?city=Cartagena&${stay}`, `/hotel/casa-aurora?${stay}`, `/book/casa-aurora?${stay}`,
    '/h/casa-aurora', `/h/casa-aurora/book?${stay}`, `/g/${portalToken}`, `/g/${portalToken}/checkin`,
  ] // prettier-ignore
  for (const path of publicRoutes) await visit(path, { label: path.replace(portalToken, ':token') })
  await visit('/embed/casa-aurora', { heading: false }) // compact search widget for the hotel's own site
  // GET /me answers 401 before logging in (A3): expected on the pages that look for a session.
  await visit('/signup', { expectHttp: [401] })
  await visit('/login', { expectHttp: [401] })
} finally {
  ws.close()
  cleanup()
}

const failed = rows.filter((row) => row.problems.length)
console.log(`\n${failed.length ? 'ROUTES WITH PROBLEMS' : 'ROUTES OK'} · ${rows.length} routes · ${failed.length} with problems · ${WIDTH}px`)
process.exit(failed.length ? 1 : 0)
