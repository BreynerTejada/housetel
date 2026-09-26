import { setupServer } from 'msw/node'

/**
 * Shared MSW server for tests. Register per-test handlers with `server.use(...)`;
 * unhandled requests fail the test (see setup.ts).
 */
export const server = setupServer()
