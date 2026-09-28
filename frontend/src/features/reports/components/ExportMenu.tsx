import { Download, FileSpreadsheet, FileText, Sheet } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { errorMessage } from '@/lib/errors'
import { downloadReport, type ExportFormat, type ReportQuery } from '../api'

const FORMATS: { format: ExportFormat; icon: typeof Sheet }[] = [
  { format: 'csv', icon: Sheet },
  { format: 'xlsx', icon: FileSpreadsheet },
  { format: 'pdf', icon: FileText },
]

/** CSV (";" + BOM, opens right in Excel in Spanish), XLSX with formats, or PDF — with the filters on screen. */
export function ExportMenu({ reportId, query, fileStem }: { reportId: string; query: ReportQuery; fileStem: string }) {
  const { t } = useTranslation('reports')
  const [busy, setBusy] = useState<ExportFormat | null>(null)

  async function run(format: ExportFormat) {
    setBusy(format)
    try {
      await downloadReport(reportId, query, format, fileStem)
      toast.success(t('export.done'))
    } catch (error) {
      toast.error(t('export.failed'), { description: errorMessage(error, t) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button loading={busy !== null}>
          <Download aria-hidden />
          {t('export.button')}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-52">
        <DropdownMenuLabel className="text-xs font-medium text-muted">{t('export.hint')}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {FORMATS.map(({ format, icon: Icon }) => (
          <DropdownMenuItem key={format} disabled={busy !== null} onSelect={() => void run(format)}>
            <Icon aria-hidden />
            {t(`export.${format}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
