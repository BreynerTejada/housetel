import { http, HttpResponse } from 'msw'

/**
 * For the tests of the app shell and the route tree (src/app/__tests__): since phase C the shell and the pages
 * they open fetch their own data (Today board and its widgets, alert bell, inbox badge, billing chip, calendar,
 * marketplace home…). Those requests are not what these tests check, so any API GET without a handler of its
 * own answers an empty 404 instead of failing the test (`onUnhandledRequest: 'error'` in setup.ts). Register it
 * first (`beforeEach`): handlers added later with `server.use()` — `mockMe()` included — take precedence.
 */
export const apiNotFoundFallback = http.get('/api/v1/*', () =>
  HttpResponse.json({ detail: 'Sin datos en este test.', code: 'not_found' }, { status: 404 }),
)
