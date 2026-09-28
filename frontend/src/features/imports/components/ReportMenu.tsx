import { ChevronDown, FileDown } from 'lucide-react'
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
import { normalizeLang } from '@/lib/format'
import { downloadReport, type JobSummary } from '../api'

/**
 * CSV report of the job (`;`, UTF-8 for Excel): one line per row with its review, dry-run and result, followed
 * by the original columns — fix the rows with errors in it and upload only those again.
 */
export function ReportMenu({ job, disabled = false }: { job: Pick<JobSummary, 'id' | 'filename' | 'data_purged'>; disabled?: boolean }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const other = lang === 'es' ? 'en' : 'es'
  const [busy, setBusy] = useState(false)

  async function get(onlyIssues: boolean, language: 'es' | 'en') {
    setBusy(true)
    try {
      await downloadReport(job, { lang: language, onlyIssues })
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" loading={busy} disabled={disabled}>
          {!busy && <FileDown aria-hidden />}
          {t('report.button')}
          <ChevronDown aria-hidden className="text-muted" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>{t('report.label')}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => void get(true, lang)}>{t('report.issues')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void get(false, lang)}>{t('report.all')}</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void get(true, other)}>{t('report.issuesOther')}</DropdownMenuItem>
        {job.data_purged && <p className="px-2 py-1.5 text-xs text-muted">{t('report.purged')}</p>}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
