import { describe, expect, it, vi } from 'vitest'
import { commands } from '../commands'

function run(id: string, query?: string) {
  const navigate = vi.fn()
  const command = commands.find((item) => item.id === id)!
  command.perform({ navigate, query })
  return { navigate, command }
}

describe('front desk commands (⌘K)', () => {
  it('"Nueva reserva" opens the wizard for whoever can book', () => {
    const { navigate, command } = run('frontdesk.newReservation')

    expect(navigate).toHaveBeenCalledWith('/app/reservations/new')
    expect(command.permission).toBe('bookings.manage')
  })

  it('"Walk-in" opens the wizard arriving now', () => {
    expect(run('frontdesk.walkIn').navigate).toHaveBeenCalledWith('/app/reservations/new?walk_in=1')
  })

  it('"Buscar reserva por código" searches the code typed in the palette', () => {
    expect(run('frontdesk.findReservation', 'reserva ht-7k2m9q').navigate).toHaveBeenCalledWith('/app/reservations?q=HT-7K2M9Q')
  })

  it('without a code it opens the list with the search box ready', () => {
    const { navigate, command } = run('frontdesk.findReservation', 'buscar reserva')

    expect(navigate).toHaveBeenCalledWith('/app/reservations?focus=search')
    expect(command.permission).toBe('bookings.view')
  })
})
