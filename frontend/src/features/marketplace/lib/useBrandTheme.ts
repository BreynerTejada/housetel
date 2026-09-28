import { useEffect } from 'react'
import { brandStyle } from './brand'

/**
 * Paints the whole document with the hotel's color while a hotel-branded page is open (booking engine, widget).
 * The variables go on `<html>` so popovers, dialogs and selects (rendered in portals) follow the brand too; the
 * previous values come back when the page closes.
 */
export function useBrandTheme(color: string | null | undefined): void {
  useEffect(() => {
    const style = brandStyle(color) as Record<string, string>
    const root = document.documentElement
    const previous = Object.keys(style).map((name) => [name, root.style.getPropertyValue(name)] as const)
    for (const [name, value] of Object.entries(style)) root.style.setProperty(name, value)
    return () => {
      for (const [name, value] of previous) {
        if (value) root.style.setProperty(name, value)
        else root.style.removeProperty(name)
      }
    }
  }, [color])
}
