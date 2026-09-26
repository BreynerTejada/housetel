import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

/** 4xx answers are final (validation, permission, not found, conflict); anything else gets one more try. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 1
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetry,
    },
    mutations: {
      retry: false,
    },
  },
})
