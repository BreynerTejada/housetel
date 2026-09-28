import { Building2, HandCoins } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// Owner: P4. ⌘K palette actions (the companies page opens the form for `?new=1`).
export const commands: CommandItem[] = [
  {
    id: 'corporate.newCompany',
    group: 'actions',
    labelKey: 'corporate:commands.newCompany',
    icon: Building2,
    keywords: ['empresa', 'company', 'nit', 'agencia', 'agency', 'corporativo'],
    permission: 'corporate.manage',
    perform: ({ navigate }) => navigate('/app/companies?new=1'),
  },
  {
    id: 'corporate.receivables',
    group: 'actions',
    labelKey: 'corporate:commands.receivables',
    icon: HandCoins,
    keywords: ['cartera', 'receivables', 'cuentas por cobrar', 'cobro', 'vencido'],
    permission: 'corporate.view',
    perform: ({ navigate }) => navigate('/app/receivables'),
  },
]
