import { Bot, FileText, LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { formatRelative, normalizeLang } from '@/lib/format'
import { aiPending, type RevenueRun } from '../api'
import { pick } from '../lib/format'

const PROVIDER_NAMES: Record<string, string> = { gemini: 'Gemini', claude: 'Claude' }

/**
 * The summary of a run: written by the LLM when it answered (badge "Resumen IA · <provider>"), else the template.
 * Right after a run the AI summary is still being written in the background: the template shows meanwhile.
 */
export function RunSummaryText({ run, className }: { run: RevenueRun; className?: string }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const fromAi = Boolean(run.ai_provider)
  const writing = !fromAi && aiPending(run)
  const text = (fromAi && pick(run.ai_summary, lang)) || pick(run.summary, lang)
  return (
    <div className={className}>
      <div aria-live="polite">
        {writing ? (
          <Badge tone="info" className="mb-2">
            <LoaderCircle aria-hidden className="animate-spin" />
            {t('lastRun.aiWriting')}
          </Badge>
        ) : (
          <Badge
            tone={fromAi ? 'info' : 'neutral'}
            className="mb-2"
            title={!fromAi && run.details?.ai_status === 'unavailable' ? t('lastRun.aiUnavailable') : undefined}
          >
            {fromAi ? <Bot aria-hidden /> : <FileText aria-hidden />}
            {fromAi ? t('lastRun.aiBadge', { provider: PROVIDER_NAMES[run.ai_provider] ?? run.ai_provider }) : t('lastRun.templateBadge')}
          </Badge>
        )}
      </div>
      <p className="max-w-3xl text-[14px] leading-6 text-fg">{text}</p>
    </div>
  )
}

export function LastRunCard({ run, today }: { run: RevenueRun | null | undefined; today?: string }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  if (run === undefined) return null
  if (run === null) {
    return (
      <div className="rounded-lg border border-dashed border-border-strong bg-surface-2/40 px-4 py-3 text-sm text-muted">
        {t('lastRun.none')}
      </div>
    )
  }
  const who = run.triggered_by?.full_name || run.triggered_by?.email
  return (
    <section aria-label={t('lastRun.title')} className="rounded-lg border border-border bg-surface px-4 py-3.5 shadow-xs sm:px-5">
      <p className="eyebrow mb-2 flex flex-wrap items-center gap-x-2">
        <span>{t('lastRun.title')}</span>
        <span aria-hidden>·</span>
        <span className="normal-case tracking-normal">{formatRelative(run.started_at, lang)}</span>
        <span aria-hidden>·</span>
        <span className="normal-case tracking-normal">
          {who ? t('lastRun.by', { trigger: t(`triggers.${run.trigger}`), who }) : t(`triggers.${run.trigger}`)}
        </span>
        {today && run.start_date && run.start_date < today && (
          <Badge tone="warning" className="ml-1 normal-case tracking-normal">
            {t('lastRun.stale')}
          </Badge>
        )}
      </p>
      <RunSummaryText run={run} />
    </section>
  )
}
