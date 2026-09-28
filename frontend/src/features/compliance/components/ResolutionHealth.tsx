import { ArrowRight, ScrollText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { formatDate, formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { ResolutionHealth } from '../api'
import { HEALTH_TONES } from '../lib/labels'

/** The DIAN numbering resolution at a glance: numbers left, validity, environment and what to do when it runs out. */
export function ResolutionHealthCard({ health, className }: { health: ResolutionHealth; className?: string }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const canConfigure = useCan('compliance.settings')
  const tone = HEALTH_TONES[health.status]
  const used = Math.min(100, Math.max(0, health.used_percent ?? 0))

  return (
    <section
      aria-label={t('resolution.title')}
      className={cn(
        'grid gap-3 rounded-xl border bg-surface p-4 shadow-xs',
        health.status === 'ok' ? 'border-border' : health.status === 'warning' ? 'border-warning/50' : 'border-danger/50',
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-lg bg-surface-2 text-muted">
            <ScrollText aria-hidden className="size-4" />
          </span>
          <div>
            <p className="text-[13px] font-semibold text-muted">{t('resolution.title')}</p>
            {health.status === 'missing' ? (
              <p className="font-semibold text-fg">{t('resolution.none')}</p>
            ) : (
              <p className="num font-semibold text-fg">
                {t('resolution.next', { prefix: health.prefix || '—', number: health.next_number })}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {health.environment && (
            <Badge tone={health.environment === 'production' ? 'info' : 'outline'}>{t(`environment.${health.environment}`)}</Badge>
          )}
          <Badge tone={tone}>{t(`resolution.health.${health.status}`)}</Badge>
        </div>
      </div>

      {health.status !== 'missing' && (
        <div className="grid gap-1.5">
          <div
            className="h-1.5 overflow-hidden rounded-full bg-surface-3"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={used}
            aria-label={t('resolution.usedLabel')}
          >
            <div
              className={cn('h-full rounded-full', health.status === 'ok' ? 'bg-success' : health.status === 'warning' ? 'bg-warning' : 'bg-danger')}
              style={{ width: `${Math.max(used, 1.5)}%` }}
            />
          </div>
          <p className="flex flex-wrap justify-between gap-x-3 text-xs text-muted">
            <span className="num">
              {t('resolution.remaining', { count: health.remaining ?? 0, formatted: formatNumber(health.remaining ?? 0, lang) })}
            </span>
            {health.valid_to && (
              <span className="num">
                {t('resolution.validTo', { date: formatDate(health.valid_to, undefined, lang), count: health.days_left ?? 0 })}
              </span>
            )}
          </p>
        </div>
      )}

      {health.status !== 'ok' && (
        <p className={cn('text-[13px]', health.status === 'warning' ? 'text-warning-ink' : 'text-danger-ink')}>
          {t(`resolution.advice.${health.status}`)}
        </p>
      )}
      {health.status !== 'ok' && canConfigure && (
        <Link
          to="/app/settings/compliance"
          className="inline-flex w-fit items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline"
        >
          {t('resolution.configure')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      )}
    </section>
  )
}
