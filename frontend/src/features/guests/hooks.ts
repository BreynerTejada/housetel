import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { fetchPrivateFile } from './api'

/** `value` after it stopped changing for `delay` ms (search boxes). */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(id)
  }, [value, delay])
  return debounced
}

/**
 * Object URL for a private file (guest documents): fetched with the session and `X-Property-Id`, since an
 * `<img src>` cannot send headers. The URL is revoked when the component unmounts or the file changes.
 */
export function usePrivateFileUrl(url: string | null | undefined) {
  const query = useQuery({
    queryKey: ['private-file', url],
    queryFn: ({ signal }) => fetchPrivateFile(url as string, signal),
    enabled: Boolean(url),
    staleTime: 5 * 60_000,
    gcTime: 60_000,
  })
  const blob = query.data
  const objectUrl = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob])
  useEffect(() => () => (objectUrl ? URL.revokeObjectURL(objectUrl) : undefined), [objectUrl])
  return { url: objectUrl, isLoading: query.isLoading, isError: query.isError, blob }
}
