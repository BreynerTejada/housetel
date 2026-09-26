import { http, HttpResponse } from 'msw'
import type { Me, Membership, PropertySummary } from '@/lib/auth'
import { server } from './server'

export const auroraProperty: PropertySummary = {
  id: '6f1c2a4e-0000-4000-8000-00000000a001',
  name: 'Hotel Casa Aurora',
  slug: 'casa-aurora',
  property_type: 'boutique',
  timezone: 'America/Bogota',
  currency: 'COP',
  business_date: '2026-09-25',
}

export const medellinProperty: PropertySummary = {
  id: '6f1c2a4e-0000-4000-8000-00000000b001',
  name: 'Andino Medellín',
  slug: 'andino-medellin',
  property_type: 'hotel',
  timezone: 'America/Bogota',
  currency: 'COP',
  business_date: '2026-09-25',
}

export const bogotaProperty: PropertySummary = {
  id: '6f1c2a4e-0000-4000-8000-00000000b002',
  name: 'Andino Hostel Bogotá',
  slug: 'andino-hostel-bogota',
  property_type: 'hostel',
  timezone: 'America/Bogota',
  currency: 'COP',
  business_date: '2026-09-26',
}

export function auroraMembership(permissions: string[] = ['*'], roleCode = 'owner'): Membership {
  return {
    organization: { id: 'org-aurora', name: 'Casa Aurora', slug: 'casa-aurora', status: 'active' },
    role: { id: `role-${roleCode}`, name: roleCode, code: roleCode },
    permissions,
    properties: [auroraProperty],
  }
}

export function andinoMembership(permissions: string[] = ['*'], roleCode = 'owner'): Membership {
  return {
    organization: { id: 'org-andino', name: 'Grupo Andino', slug: 'grupo-andino', status: 'active' },
    role: { id: `role-andino-${roleCode}`, name: roleCode, code: roleCode },
    permissions,
    properties: [medellinProperty, bogotaProperty],
  }
}

/** A signed-in user with the exact `Me` shape (spec §3 + `phone`). Defaults: owner of Casa Aurora. */
export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: 'user-1',
    email: 'owner@casaaurora.co',
    full_name: 'Valentina Ríos',
    language: 'es',
    phone: '',
    is_platform_admin: false,
    memberships: [auroraMembership()],
    ...overrides,
  }
}

/** Answers `GET /api/v1/accounts/me/` with a user, or as DRF does for anonymous sessions (`null`). */
export function mockMe(me: Me | null) {
  server.use(
    http.get('/api/v1/accounts/me/', () =>
      me
        ? HttpResponse.json(me)
        : HttpResponse.json(
            { detail: 'Las credenciales de autenticación no se proveyeron.', code: 'not_authenticated' },
            { status: 403 },
          ),
    ),
  )
}
