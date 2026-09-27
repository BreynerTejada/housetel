import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { toast } from 'sonner'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import i18n from '@/lib/i18n'
import { server } from './server'

// Routes load pages and shells lazily; the first import of a module graph in a test file can take a
// few seconds to transform, so `findBy*` waits longer than the 1 s default.
configure({ asyncUtilTimeout: 8000 })

// --- jsdom gaps used by Radix, cmdk and the theme provider -------------------------------------
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => undefined
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => undefined
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => undefined

// --- MSW: every request must be handled by the test ---------------------------------------------
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

// Tests read Spanish UI text unless they switch language on purpose.
beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  server.resetHandlers()
  // Sonner keeps active toasts in a module-level store and replays them to the next <Toaster> that mounts:
  // without this a toast left open by one test shows up in the next one.
  toast.dismiss()
})

afterAll(() => {
  server.close()
})
