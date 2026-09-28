import { KeyRound, ShieldCheck, UserPlus } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `team` feature (plan §E). Owner: B3 (users, roles) and P2 (account: every signed-in
// user, so it has no permission; it also makes the settings entry visible to every role. Platform super-admins
// get it in their own area, since they have no hotel).
export const nav: NavItem[] = [
  { id: 'account', section: 'settings', labelKey: 'team:nav.account', icon: ShieldCheck, path: '/app/settings/account', order: 5, descriptionKey: 'team:nav.accountHint' },
  { id: 'users', section: 'settings', labelKey: 'team:nav.users', icon: UserPlus, path: '/app/settings/users', permission: 'accounts.users_manage', order: 130, descriptionKey: 'team:nav.usersHint' },
  { id: 'roles', section: 'settings', labelKey: 'team:nav.roles', icon: KeyRound, path: '/app/settings/roles', permission: 'accounts.roles_manage', order: 140, descriptionKey: 'team:nav.rolesHint' },
  { id: 'adminAccount', section: 'admin', labelKey: 'team:nav.account', icon: ShieldCheck, path: '/admin/account', order: 90, platformAdmin: true },
]
