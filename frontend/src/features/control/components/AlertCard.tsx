import { ArrowUpRight, Check } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Alert } from '../api'
import { alertKindLabel, plainText } from '../lib/labels'
import { SeverityBadge, SeverityRail } from './severity'

interface Props {
  alert: Alert
  selected?: boolean
  onSelectedChange?: (selected: boolean) => void
  onResolve?: () => void
  resolving?: boolean
  canResolve: boolean
}

/** One alert: severity (rail + badge), what happened, where to fix it ("Ver dónde") and "Resolver". */
export function AlertCard({ alert, selected = false, onSelectedChange, onResolve, resolving = false, canResolve }: Props) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const resolved = alert.resolved_at !== null

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        'relative grid gap-2 rounded-xl border bg-surface py-3.5 pr-3.5 pl-5 shadow-xs transition-colors sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-4 sm:py-4 sm:pr-4',
        selected ? 'border-accent/50 bg-accent-soft/30' : 'border-border',
        resolved && 'bg-surface-2/50 shadow-none',
      )}
    >
      {!resolved && <SeverityRail severity={alert.severity} />}
      <div className="flex min-w-0 gap-3">
        {onSelectedChange && !resolved && (
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onSelectedChange(checked === true)}
            aria-label={t('alerts.select', { title: alert.title })}
            className="mt-0.5"
          />
        )}
        <div className="grid min-w-0 gap-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <SeverityBadge severity={alert.severity} className={cn(resolved && 'opacity-70')} />
            <span className="text-xs font-semibold text-muted">{alertKindLabel(t, i18n, alert.kind)}</span>
          </div>
          <h3 id={titleId} className={cn('text-[15px] leading-5 font-bold break-words', resolved ? 'text-muted' : 'text-fg')}>
            {alert.title}
          </h3>
          {alert.message && <p className="line-clamp-3 text-[13px] break-words whitespace-pre-line text-fg/80">{plainText(alert.message)}</p>}
          <p className="text-xs text-muted">
            {resolved
              ? alert.resolved_by
                ? t('alerts.resolvedBy', { name: alert.resolved_by.name, when: formatRelative(alert.resolved_at, lang) })
                : t('alerts.resolvedAuto', { when: formatRelative(alert.resolved_at, lang) })
              : alert.updated_at !== alert.created_at
                ? t('alerts.updated', { when: formatRelative(alert.updated_at, lang) })
                : t('alerts.created', { when: formatRelative(alert.created_at, lang) })}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 sm:flex-col sm:items-end sm:justify-center">
        {alert.link && (
          <Button asChild size="sm" variant="ghost">
            <Link to={alert.link}>
              {t('alerts.open')}
              <ArrowUpRight aria-hidden />
            </Link>
          </Button>
        )}
        {!resolved && canResolve && onResolve && (
          <Button size="sm" onClick={onResolve} loading={resolving}>
            {!resolving && <Check aria-hidden />}
            {t('alerts.resolve')}
          </Button>
        )}
      </div>
    </article>
  )
}
