import type { Invitation, Member, Role } from '../api'

export function makeRole(overrides: Partial<Role> = {}): Role {
  return {
    id: 'role-front',
    code: 'front_desk',
    name: 'Recepción',
    is_system: true,
    description: 'Reservas, check-in/out, huéspedes, cobros y caja.',
    permissions: ['frontdesk.view', 'bookings.view', 'bookings.manage', 'guests.view'],
    members_count: 1,
    assignable: true,
    editable: false,
    created_at: '2026-09-01T10:00:00-05:00',
    ...overrides,
  }
}

export const ownerRole = makeRole({
  id: 'role-owner',
  code: 'owner',
  name: 'Dueño',
  permissions: ['*'],
  description: 'Acceso total a la organización.',
})

export function makeMember(overrides: Partial<Member> = {}): Member {
  return {
    id: 'member-andres',
    user: { id: 'user-andres', email: 'recepcion@casaaurora.co', full_name: 'Andrés Gómez', phone: '', last_login: null },
    role: { id: 'role-front', code: 'front_desk', name: 'Recepción', is_system: true },
    all_properties: true,
    properties: [],
    is_active: true,
    is_owner: false,
    is_self: false,
    editable: true,
    created_at: '2026-09-01T10:00:00-05:00',
    ...overrides,
  }
}

export function makeInvitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: 'inv-1',
    email: 'nocturno@casaaurora.co',
    role: { id: 'role-front', code: 'front_desk', name: 'Recepción', is_system: true },
    all_properties: true,
    properties: [],
    status: 'pending',
    expires_at: '2026-10-02T10:00:00-05:00',
    invited_by: { id: 'user-1', full_name: 'Valentina Ríos', email: 'owner@casaaurora.co' },
    created_at: '2026-09-25T10:00:00-05:00',
    invite_url: 'http://localhost:5173/invite/tok-123',
    editable: true,
    ...overrides,
  }
}
