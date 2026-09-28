import { ChevronDown, Download, FileSpreadsheet, Sparkles } from 'lucide-react'
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
import { downloadTemplate, type ImportKind, type ImportPreset } from '../api'

/**
 * Empty templates (Housetel's column titles, recognized automatically) in Spanish or English, and an example
 * file built from this property's categories, rooms and dates — the quickest way to try the importer.
 */
export function TemplatesMenu({ kind, preset }: { kind: ImportKind; preset: ImportPreset }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const [busy, setBusy] = useState(false)
  const cloudbedsExample = preset === 'cloudbeds' && (kind === 'reservations' || kind === 'guests')

  async function get(options: Parameters<typeof downloadTemplate>[1]) {
    setBusy(true)
    try {
      await downloadTemplate(kind, options)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="secondary" loading={busy}>
          {!busy && <Download aria-hidden />}
          {t('templates.button')}
          <ChevronDown aria-hidden className="text-muted" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>{t('templates.empty', { kind: t(`kinds.${kind}.label`) })}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => void get({ lang: 'es', format: 'xlsx' })}>
          <FileSpreadsheet aria-hidden /> {t('templates.esXlsx')}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void get({ lang: 'es', format: 'csv' })}>
          <FileSpreadsheet aria-hidden /> {t('templates.esCsv')}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void get({ lang: 'en', format: 'xlsx' })}>
          <FileSpreadsheet aria-hidden /> {t('templates.enXlsx')}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void get({ lang: 'en', format: 'csv' })}>
          <FileSpreadsheet aria-hidden /> {t('templates.enCsv')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t('templates.exampleLabel')}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => void get({ lang, format: 'xlsx', example: true })}>
          <Sparkles aria-hidden /> {t('templates.example')}
        </DropdownMenuItem>
        {cloudbedsExample && (
          <DropdownMenuItem onSelect={() => void get({ lang, format: 'xlsx', example: true, preset: 'cloudbeds' })}>
            <Sparkles aria-hidden /> {t('templates.exampleCloudbeds')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
