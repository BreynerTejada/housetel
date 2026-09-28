import { useEffect, useState } from 'react'

/**
 * Width of an element that is attached with the returned callback ref, kept up to date by a ResizeObserver
 * (browsers report the first size as soon as it is observed). It stays 0 where nothing is laid out, e.g. in
 * jsdom: callers fall back to their minimum sizes.
 */
export function useElementWidth<T extends HTMLElement>(): [ref: (element: T | null) => void, width: number, element: T | null] {
  const [element, setElement] = useState<T | null>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(Math.round(entry.contentRect.width))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])
  return [setElement, width, element]
}
