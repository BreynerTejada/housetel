import { FileSpreadsheet, ReceiptText } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// Owner: C7. ⌘K palette actions (navigation items come from nav.ts).
export const commands: CommandItem[] = [
  {
    id: 'compliance-generate-sire',
    group: 'actions',
    labelKey: 'compliance:commands.generateSire',
    icon: FileSpreadsheet,
    keywords: ['sire', 'migración', 'migracion', 'extranjeros', 'foreigners'],
    permission: 'compliance.sire',
    perform: ({ navigate }) => navigate('/app/compliance?tab=sire'),
  },
  {
    id: 'compliance-pending',
    group: 'actions',
    labelKey: 'compliance:commands.pending',
    icon: ReceiptText,
    keywords: ['dian', 'factura', 'invoice', 'tra', 'legal'],
    permission: 'compliance.view',
    perform: ({ navigate }) => navigate('/app/compliance?tab=pending'),
  },
]
