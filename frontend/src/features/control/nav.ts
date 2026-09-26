import { Bell, FileClock, Plug, Workflow } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `control` feature (plan §E). Owner: C12.
export const nav: NavItem[] = [
  { id: 'alerts', section: 'insights', labelKey: 'control:nav.alerts', icon: Bell, path: '/app/alerts', permission: 'control.alerts', order: 20 },
  { id: 'integrations', section: 'settings', labelKey: 'control:nav.integrations', icon: Plug, path: '/app/settings/integrations', permission: 'control.integrations', order: 150, descriptionKey: 'control:nav.integrationsHint' },
  { id: 'automations', section: 'settings', labelKey: 'control:nav.automations', icon: Workflow, path: '/app/settings/automations', permission: 'control.automations', order: 160, descriptionKey: 'control:nav.automationsHint' },
  { id: 'audit', section: 'settings', labelKey: 'control:nav.audit', icon: FileClock, path: '/app/settings/audit', permission: 'control.audit', order: 170, descriptionKey: 'control:nav.auditHint' },
]
