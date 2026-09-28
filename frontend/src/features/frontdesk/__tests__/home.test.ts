import { ClipboardList, Sun, Wallet } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import type { NavItem } from '@/app/extensions'
import { matchPermission } from '@/lib/permissions'
import { landingFor } from '../lib/home'

const can = (granted: string[]) => (code?: string) => !code || matchPermission(granted, code)

const nav: NavItem[] = [
  { id: 'today', section: 'operations', labelKey: 'frontdesk:nav.today', icon: Sun, path: '/app', permission: 'frontdesk.view' },
  { id: 'reservations', section: 'operations', labelKey: 'x', icon: ClipboardList, path: '/app/reservations', permission: 'bookings.view' },
  { id: 'cashier', section: 'operations', labelKey: 'x', icon: Wallet, path: '/app/cashier', permission: 'finance.view' },
]

describe('landingFor', () => {
  it('keeps whoever runs the front desk on Today', () => {
    expect(landingFor(can(['frontdesk.view', 'housekeeping.work']), nav)).toBeNull()
  })

  it('sends a housekeeper straight to their rooms', () => {
    expect(landingFor(can(['housekeeping.view', 'housekeeping.work', 'inventory.view']), nav)).toBe('/app/housekeeping/mine')
  })

  it('sends a housekeeping supervisor to the board', () => {
    expect(landingFor(can(['housekeeping.*', 'inventory.view']), nav)).toBe('/app/housekeeping')
  })

  it('sends maintenance to the tickets', () => {
    expect(landingFor(can(['housekeeping.view', 'housekeeping.maintenance']), nav)).toBe('/app/maintenance')
  })

  it('sends anyone else to the first page they can open', () => {
    expect(landingFor(can(['finance.*', 'reports.*', 'bookings.view']), nav)).toBe('/app/reservations')
    expect(landingFor(can(['finance.view']), nav)).toBe('/app/cashier')
  })

  it('stays put when there is nowhere else to go', () => {
    expect(landingFor(can(['guests.view']), nav)).toBeNull()
  })
})
