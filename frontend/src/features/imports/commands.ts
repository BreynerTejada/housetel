import { Import } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// Owner: P5. ⌘K palette: jump to the importer.
export const commands: CommandItem[] = [
  {
    id: 'imports.open',
    group: 'actions',
    labelKey: 'imports:commands.import',
    icon: Import,
    keywords: ['importar', 'import', 'migrar', 'migración', 'cloudbeds', 'excel', 'csv', 'plantilla', 'template'],
    permission: 'imports.run',
    perform: ({ navigate }) => navigate('/app/settings/import'),
  },
]
