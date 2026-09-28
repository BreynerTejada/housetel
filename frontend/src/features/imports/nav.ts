import { Import } from 'lucide-react'
import type { NavItem } from '@/app/extensions'

// Owner: P5. Data import from another PMS (Cloudbeds export, Excel/CSV): wizard and history of jobs.
export const nav: NavItem[] = [
  {
    id: 'import',
    section: 'settings',
    labelKey: 'imports:nav.import',
    icon: Import,
    path: '/app/settings/import',
    permission: 'imports.run',
    order: 145,
    descriptionKey: 'imports:nav.importHint',
  },
]
