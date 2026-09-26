import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { queryClient, shouldRetry } from '@/lib/query'

describe('query retry policy', () => {
  it('never retries client errors (validation, permission, not found, conflict)', () => {
    for (const status of [400, 401, 402, 403, 404, 409, 429]) {
      expect(shouldRetry(0, new ApiError(status, 'x', 'x'))).toBe(false)
    }
  })

  it('retries server and network errors exactly once', () => {
    expect(shouldRetry(0, new ApiError(502, 'http_error', 'Bad gateway'))).toBe(true)
    expect(shouldRetry(0, new ApiError(0, 'network_error', 'offline'))).toBe(true)
    expect(shouldRetry(1, new ApiError(502, 'http_error', 'Bad gateway'))).toBe(false)
  })

  it('is the default for app queries, with a 30 s stale time', () => {
    const defaults = queryClient.getDefaultOptions().queries
    expect(defaults?.retry).toBe(shouldRetry)
    expect(defaults?.staleTime).toBe(30_000)
  })
})
