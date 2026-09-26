import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { THEME_STORAGE_KEY, ThemeProvider, useTheme } from '@/lib/theme'

/** Controllable `prefers-color-scheme: dark` media query. */
function mockSystemDark(initial: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>()
  const mql = {
    matches: initial,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  }
  window.matchMedia = ((query: string) =>
    query.includes('prefers-color-scheme: dark') ? mql : { ...mql, matches: false, media: query }) as typeof window.matchMedia
  return {
    set(dark: boolean) {
      mql.matches = dark
      listeners.forEach((cb) => cb({ matches: dark } as MediaQueryListEvent))
    },
  }
}

function Probe() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme('dark')}>dark</button>
      <button onClick={() => setTheme('light')}>light</button>
      <button onClick={() => setTheme('system')}>system</button>
    </div>
  )
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('ThemeProvider', () => {
  it('applies the saved preference to <html data-theme>', () => {
    mockSystemDark(false)
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
  })

  it('defaults to the system preference', () => {
    mockSystemDark(true)

    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(screen.getByTestId('theme')).toHaveTextContent('system')
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('switches theme and remembers the choice', async () => {
    mockSystemDark(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    await userEvent.click(screen.getByRole('button', { name: 'dark' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')

    await userEvent.click(screen.getByRole('button', { name: 'light' }))

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  it('follows OS changes only while the preference is system', async () => {
    const system = mockSystemDark(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)
    expect(document.documentElement.dataset.theme).toBe('light')

    act(() => system.set(true))
    expect(document.documentElement.dataset.theme).toBe('dark')

    await userEvent.click(screen.getByRole('button', { name: 'light' }))
    act(() => system.set(true))
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
