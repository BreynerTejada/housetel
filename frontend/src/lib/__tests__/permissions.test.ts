import { describe, expect, it } from 'vitest'
import { matchPermission } from '@/lib/permissions'

// Same semantics as backend apps/core/permissions.codes_match:
//   any(g == "*" or g == code or fnmatchcase(code, g) for g in granted or [])

describe('matchPermission (backend parity)', () => {
  it('grants everything with *', () => {
    expect(matchPermission(['*'], 'finance.refund')).toBe(true)
  })

  it('matches exact codes', () => {
    expect(matchPermission(['bookings.view'], 'bookings.view')).toBe(true)
    expect(matchPermission(['bookings.view'], 'bookings.manage')).toBe(false)
  })

  it('matches app wildcards', () => {
    expect(matchPermission(['bookings.*'], 'bookings.manage')).toBe(true)
    expect(matchPermission(['bookings.*'], 'guests.view')).toBe(false)
  })

  it('does not match the bare app name against app.*', () => {
    expect(matchPermission(['bookings.*'], 'bookings')).toBe(false)
  })

  it('treats dots in grants literally', () => {
    expect(matchPermission(['bookings.view'], 'bookingsXview')).toBe(false)
    expect(matchPermission(['bookings.*'], 'bookingsXmanage')).toBe(false)
  })

  it('treats other regex metacharacters literally', () => {
    expect(matchPermission(['a+b'], 'aab')).toBe(false)
    expect(matchPermission(['a+b'], 'a+b')).toBe(true)
  })

  it('supports wildcards in any position', () => {
    expect(matchPermission(['*.view'], 'guests.view')).toBe(true)
    expect(matchPermission(['*.view'], 'guests.manage')).toBe(false)
  })

  it('supports fnmatch ? and character classes', () => {
    expect(matchPermission(['finance.re?und'], 'finance.refund')).toBe(true)
    expect(matchPermission(['finance.[vc]*'], 'finance.void')).toBe(true)
    expect(matchPermission(['finance.[vc]*'], 'finance.collect')).toBe(true)
    expect(matchPermission(['finance.[vc]*'], 'finance.refund')).toBe(false)
    expect(matchPermission(['finance.[!v]*'], 'finance.void')).toBe(false)
    expect(matchPermission(['finance.[!v]*'], 'finance.collect')).toBe(true)
  })

  it('is case sensitive like fnmatchcase', () => {
    expect(matchPermission(['Bookings.view'], 'bookings.view')).toBe(false)
  })

  it('denies with empty or missing grants', () => {
    expect(matchPermission([], 'bookings.view')).toBe(false)
    expect(matchPermission(undefined, 'bookings.view')).toBe(false)
    expect(matchPermission(null, 'bookings.view')).toBe(false)
  })
})

describe('matchPermission with the system role templates (plan §D)', () => {
  const manager = [
    'accounts.*', 'inventory.*', 'rates.*', 'bookings.*', 'guests.*', 'finance.*', 'frontdesk.*',
    'housekeeping.*', 'distribution.*', 'marketplace.*', 'guestportal.*', 'messaging.*',
    'compliance.*', 'revenue.*', 'ai.*', 'reports.*', 'control.*', 'saas.billing_view',
  ]
  const frontDesk = [
    'frontdesk.view', 'bookings.view', 'bookings.manage', 'bookings.checkin', 'bookings.cancel',
    'guests.view', 'guests.manage', 'finance.view', 'finance.collect', 'finance.cashier',
    'messaging.view', 'messaging.send', 'guestportal.view', 'guestportal.manage',
    'housekeeping.view', 'compliance.view', 'compliance.invoice', 'compliance.sire', 'compliance.tra',
    'reports.operational', 'ai.copilot', 'control.alerts', 'inventory.view', 'rates.view',
    'distribution.view', 'revenue.view',
  ]

  it('lets the manager undo audit events but not manage SaaS billing', () => {
    expect(matchPermission(manager, 'control.audit_undo')).toBe(true)
    expect(matchPermission(manager, 'saas.billing_view')).toBe(true)
    expect(matchPermission(manager, 'saas.billing_manage')).toBe(false)
  })

  it('lets front desk check guests in but not waive fees or refund', () => {
    expect(matchPermission(frontDesk, 'bookings.checkin')).toBe(true)
    expect(matchPermission(frontDesk, 'bookings.waive_fee')).toBe(false)
    expect(matchPermission(frontDesk, 'finance.refund')).toBe(false)
  })
})
