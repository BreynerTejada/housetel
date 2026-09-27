/**
 * Roles store permission codes or fnmatch patterns (`bookings.*`, `*`). The matrix works on explicit
 * codes: a pattern shows every code it grants as checked, and the first edit expands it into those codes.
 */
import { matchPermission } from '@/lib/permissions'
import type { PermissionModule } from './api'

export type ModuleState = 'all' | 'some' | 'none'

export function catalogCodes(catalog: PermissionModule[]): string[] {
  return catalog.flatMap((module) => module.permissions.map((permission) => permission.code))
}

/** Catalog codes granted by `value` (codes and patterns), sorted. */
export function expandPermissions(value: readonly string[], catalog: PermissionModule[]): string[] {
  return catalogCodes(catalog)
    .filter((code) => matchPermission(value, code))
    .sort()
}

export function moduleCoverage(value: readonly string[], module: PermissionModule): { granted: number; total: number; state: ModuleState } {
  const total = module.permissions.length
  const granted = module.permissions.filter((permission) => matchPermission(value, permission.code)).length
  return { granted, total, state: granted === 0 ? 'none' : granted === total ? 'all' : 'some' }
}

export function togglePermission(value: readonly string[], code: string, on: boolean, catalog: PermissionModule[]): string[] {
  const codes = new Set(expandPermissions(value, catalog))
  if (on) codes.add(code)
  else codes.delete(code)
  return [...codes].sort()
}

/** Turns a whole module on or off; permissions the user cannot grant are left as they are. */
export function toggleModule(
  value: readonly string[],
  module: PermissionModule,
  on: boolean,
  catalog: PermissionModule[],
  canGrant: (code: string) => boolean = () => true,
): string[] {
  const codes = new Set(expandPermissions(value, catalog))
  for (const { code } of module.permissions) {
    if (!canGrant(code)) continue
    if (on) codes.add(code)
    else codes.delete(code)
  }
  return [...codes].sort()
}
