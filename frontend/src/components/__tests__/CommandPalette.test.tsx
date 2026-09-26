import { screen } from '@testing-library/react'
import { CalendarDays, Plus, Tags } from 'lucide-react'
import { describe, expect, it, vi } from 'vitest'
import type { CommandItem, NavItem } from '@/app/extensions'
import { CommandPalette, CommandPaletteList } from '@/components/CommandPalette'
import { auroraMembership, makeMe, mockMe } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const nav: NavItem[] = [
  { id: 'calendar', section: 'operations', labelKey: 'calendar:nav.calendar', icon: CalendarDays, path: '/app/calendar' },
  { id: 'rates', section: 'revenue', labelKey: 'rates:nav.rates', icon: Tags, path: '/app/rates' },
]

describe('CommandPaletteList', () => {
  it('lists pages and actions, and filters as the user types', async () => {
    const commands: CommandItem[] = [
      { id: 'new-reservation', group: 'actions', labelKey: 'frontdesk:pages.newReservation', icon: Plus, perform: vi.fn() },
    ]
    const { user } = renderWithProviders(<CommandPaletteList nav={nav} commands={commands} onDone={vi.fn()} />)

    expect(screen.getByRole('option', { name: 'Calendario' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Tarifas' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Nueva reserva' })).toBeInTheDocument()

    await user.type(screen.getByRole('combobox'), 'tarif')

    expect(screen.getByRole('option', { name: 'Tarifas' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Calendario' })).not.toBeInTheDocument()
  })

  it('navigates to the chosen page and closes', async () => {
    const onDone = vi.fn()
    const { user, router } = renderWithProviders(<CommandPaletteList nav={nav} commands={[]} onDone={onDone} />, {
      route: '/app',
    })

    await user.click(screen.getByRole('option', { name: 'Tarifas' }))

    expect(router.state.location.pathname).toBe('/app/rates')
    expect(onDone).toHaveBeenCalled()
  })

  it('runs an action with navigation and the typed text', async () => {
    const perform = vi.fn()
    const commands: CommandItem[] = [{ id: 'ask', group: 'actions', labelKey: 'frontdesk:pages.newReservation', keywords: ['ask'], perform }]
    const { user } = renderWithProviders(<CommandPaletteList nav={[]} commands={commands} onDone={vi.fn()} />)

    await user.type(screen.getByRole('combobox'), 'ask')
    await user.click(screen.getByRole('option', { name: 'Nueva reserva' }))

    expect(perform).toHaveBeenCalledWith({ navigate: expect.any(Function), query: 'ask' })
  })
})

describe('CommandPalette', () => {
  it('only offers pages the signed-in role can open', async () => {
    mockMe(makeMe({ memberships: [auroraMembership(['housekeeping.view', 'housekeeping.work', 'inventory.view'], 'housekeeping')] }))
    renderWithProviders(<CommandPalette open onOpenChange={vi.fn()} />, { route: '/app' })

    expect(await screen.findByRole('option', { name: 'Limpieza' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Calendario' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Tarifas' })).not.toBeInTheDocument()
  })
})
