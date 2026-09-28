import { Globe, Network } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Final nav items of the `channels` feature (plan §E). Owner: C3.
export const nav: NavItem[] = [
  { id: 'channels', section: 'revenue', labelKey: 'channels:nav.channels', icon: Network, path: '/app/channels', permission: 'distribution.view', order: 50 },
  // Development/demo tool: hidden where simulations are off (production), plan P6.
  { id: 'otaSim', section: 'tools', labelKey: 'channels:nav.otaSim', icon: Globe, path: '/app/simulators/ota', permission: 'distribution.manage', order: 30, devOnly: true },
]
