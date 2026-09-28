import { useTranslation } from 'react-i18next'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Tone } from '../lib/fields'

export interface LedgerSegment {
  key: string
  label: string
  count: number
  tone: Tone
  /** Diagonal hatch (rolled back). */
  hatched?: boolean
}

const BAR: Record<Tone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  stone: 'bg-stone',
  info: 'bg-info',
  accent: 'bg-accent',
  neutral: 'bg-border-strong',
}

const EDGE: Record<Tone, string> = {
  success: 'border-l-success',
  warning: 'border-l-warning',
  danger: 'border-l-danger',
  stone: 'border-l-stone',
  info: 'border-l-info',
  accent: 'border-l-accent',
  neutral: 'border-l-border-strong',
}

/**
 * The file, row by row: one strip split by what happens to each row (ready / warning / error / skipped in the
 * review, would create / update / skip / fail in the dry-run, created / updated / skipped / failed after the
 * import). The tallies below double as filters of the row list when `onSelect` is given.
 */
export function RowLedger({
  segments,
  total,
  caption,
  active = null,
  onSelect,
  className,
}: {
  segments: LedgerSegment[]
  total: number
  caption: string
  active?: string | null
  onSelect?: (key: string | null) => void
  className?: string
}) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const sum = Math.max(total, segments.reduce((acc, segment) => acc + segment.count, 0), 1)

  return (
    <section aria-label={caption} className={cn('grid gap-3', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">{caption}</p>
        <p className="num text-[13px] font-semibold text-muted">{t('ledger.rows', { count: total, formatted: formatNumber(total, lang, 0) })}</p>
      </div>
      <div aria-hidden className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-surface-3">
        {segments
          .filter((segment) => segment.count > 0)
          .map((segment) => (
            <span
              key={segment.key}
              className={cn(
                'h-full min-w-1 transition-[width,opacity] duration-500 ease-out first:rounded-l-full last:rounded-r-full',
                BAR[segment.tone],
                segment.hatched && 'hatch',
                active && active !== segment.key && 'opacity-35',
              )}
              style={{ width: `${(segment.count / sum) * 100}%` }}
            />
          ))}
      </div>
      <div
        className={cn(
          'grid grid-cols-2 gap-2',
          segments.length >= 5 ? 'sm:grid-cols-3 lg:grid-cols-5' : segments.length === 4 ? 'sm:grid-cols-4' : 'sm:grid-cols-3',
        )}
      >
        {segments.map((segment) => {
          const selected = active === segment.key
          const percent = Math.round((segment.count / sum) * 100)
          const body = (
            <>
              <span className="num block text-xl leading-7 font-bold tracking-[-0.02em] text-fg">{formatNumber(segment.count, lang, 0)}</span>
              <span className="block text-xs leading-4 font-semibold text-muted">{segment.label}</span>
              <span className="num mt-0.5 block text-[11px] text-subtle">{percent} %</span>
            </>
          )
          const classes = cn(
            'rounded-lg border border-border border-l-[3px] bg-surface px-3 py-2 text-left shadow-xs',
            EDGE[segment.tone],
            selected && 'bg-surface-2 ring-1 ring-border-strong',
          )
          if (!onSelect) {
            return (
              <div key={segment.key} className={classes}>
                {body}
              </div>
            )
          }
          return (
            <button
              key={segment.key}
              type="button"
              aria-pressed={selected}
              disabled={segment.count === 0 && !selected}
              onClick={() => onSelect(selected ? null : segment.key)}
              className={cn(
                classes,
                'transition-[background-color,box-shadow] hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:cursor-default disabled:opacity-60 disabled:hover:bg-surface',
              )}
            >
              {body}
              <span className="sr-only">{selected ? t('ledger.showingOnly') : t('ledger.filter')}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
