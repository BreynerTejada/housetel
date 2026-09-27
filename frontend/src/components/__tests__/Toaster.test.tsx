import { act, screen } from '@testing-library/react'
import { toast } from 'sonner'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'

// Sonner keeps the active toasts in a module-level store and replays them to every <Toaster> that mounts, so a
// toast still open when a test ended used to show up in the next test. The shared setup (src/test/setup.ts)
// dismisses every toast after each test. These two tests run in order.
describe('toasts across tests', () => {
  it('shows a toast', async () => {
    renderWithProviders(<p>página</p>)
    act(() => {
      toast.success('Guardado en el test anterior')
    })
    expect(await screen.findByText('Guardado en el test anterior')).toBeInTheDocument()
  })

  it('does not inherit the toasts of the previous test', async () => {
    renderWithProviders(<p>página</p>)
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(screen.queryByText('Guardado en el test anterior')).not.toBeInTheDocument()
  })
})
