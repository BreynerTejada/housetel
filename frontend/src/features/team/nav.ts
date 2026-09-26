import { KeyRound, UserPlus } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `team` feature (plan §E). Owner: B3.
export const nav: NavItem[] = [
  { id: 'users', section: 'settings', labelKey: 'team:nav.users', icon: UserPlus, path: '/app/settings/users', permission: 'accounts.users_manage', order: 130, descriptionKey: 'team:nav.usersHint' },
  { id: 'roles', section: 'settings', labelKey: 'team:nav.roles', icon: KeyRound, path: '/app/settings/roles', permission: 'accounts.roles_manage', order: 140, descriptionKey: 'team:nav.rolesHint' },
]
