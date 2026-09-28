import { BookOpenText, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * "How it is calculated": the definitions the backend used for these exact figures (range, comparison,
 * what counts as sold, forecast…). Open by default on wide screens would crowd the page, so it folds.
 */
export function ReportNotes({ notes, generatedAt }: { notes: string[]; generatedAt?: string }) {
  const { t, i18n } = useTranslation('reports')
  if (notes.length === 0) return null
  const generated = generatedAt
    ? new Intl.DateTimeFormat(i18n.language.startsWith('en') ? 'en-US' : 'es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(generatedAt))
    : null

  return (
    <details className="group rounded-lg border border-border bg-surface-2/50 open:bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <BookOpenText aria-hidden className="size-4 shrink-0 text-muted" />
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-bold text-fg">{t('notes.title')}</span>
          <span className="block text-xs text-muted">{t('notes.subtitle')}</span>
        </span>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-subtle transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-border px-4 py-3">
        <ul className="grid max-w-3xl gap-2.5 text-[13px] leading-5 text-muted">
          {notes.map((note, index) => (
            <li key={index} className="flex gap-2.5">
              <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-border-strong" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
        {generated && <p className="mt-3 text-xs text-subtle">{t('report.generated', { time: generated })}</p>}
      </div>
    </details>
  )
}
