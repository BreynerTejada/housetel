import { ArrowRight, Bot, Check, MousePointerClick, RotateCcw, ShieldCheck, Sparkles, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useExplain, useRecommendation, type Decision, type Recommendation, type RecommendationStatus } from '../api'
import { pick, signedPercent } from '../lib/format'
import { percent, reasonLine } from '../lib/labels'
import { STEP_CLASS, stepOf } from '../lib/scale'
import { KindIcon } from './KindIcon'

const STATUS_TONE: Record<RecommendationStatus, BadgeTone> = {
  pending: 'accent',
  approved: 'warning',
  rejected: 'stone',
  applied: 'success',
  auto_applied: 'success',
  expired: 'neutral',
}

export interface RecommendationDetailProps {
  id: string | null
  currency: string
  canManage: boolean
  pending: Decision | null
  onDecide: (decision: Decision, ids: string[]) => void
  className?: string
}

/** Why the price of one night should move: the change, what the rules saw, the limits and the explanation. */
export function RecommendationDetail({ id, currency, canManage, pending, onDecide, className }: RecommendationDetailProps) {
  const { t } = useTranslation('revenue')
  const query = useRecommendation(id)
  return (
    <section aria-label={t('detail.label')} className={cn('rounded-lg border border-border bg-surface shadow-xs', className)}>
      {!id ? (
        <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
          <span className="grid size-10 place-items-center rounded-xl border border-border bg-surface-2 text-muted">
            <MousePointerClick aria-hidden className="size-5" />
          </span>
          <p className="mt-1 font-semibold text-fg">{t('detail.emptyTitle')}</p>
          <p className="max-w-xs text-sm text-muted">{t('detail.emptyHint')}</p>
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <div className="grid gap-3 p-5">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-10 w-56" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <DetailBody key={query.data.id} rec={query.data} currency={currency} canManage={canManage} pending={pending} onDecide={onDecide} />
      )}
    </section>
  )
}

function DetailBody({
  rec,
  currency,
  canManage,
  pending,
  onDecide,
}: {
  rec: Recommendation
  currency: string
  canManage: boolean
  pending: Decision | null
  onDecide: (decision: Decision, ids: string[]) => void
}) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const reasons = rec.reasons.map((reason) => ({ reason, line: reasonLine(t, reason, lang, currency) }))
  const ruleReasons = reasons.filter((item) => item.reason.type === 'rule')
  const limitReasons = reasons.filter((item) => item.reason.type === 'limit')
  const step = stepOf(rec.change_percent)
  const decidedBy = rec.decided_by?.full_name || rec.decided_by?.email
  const id = rec.id ?? ''

  return (
    <div className="grid gap-4 p-4 sm:p-5">
      <header className="grid gap-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[13px] font-bold text-fg">
              <span aria-hidden className="h-4 w-1 rounded-full" style={{ background: rec.room_type.color }} />
              <span className="truncate">{pick(rec.room_type.name, lang)}</span>
              <span className="font-semibold text-muted">· {rec.rate_plan.code}</span>
            </p>
            <p className="text-sm text-muted first-letter:uppercase">{formatDate(rec.date, 'EEEE d MMMM yyyy', lang)}</p>
          </div>
          <Badge tone={STATUS_TONE[rec.status]}>{t(`statusBadge.${rec.status}`)}</Badge>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
        <span className="num text-sm text-muted line-through decoration-1">{formatMoney(rec.current_price, currency)}</span>
        <ArrowRight aria-hidden className="mb-1 size-4 text-subtle" />
        <span className="text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">{formatMoney(rec.recommended_price, currency)}</span>
        <span className={cn('mb-1 rounded-md px-1.5 py-0.5 text-xs font-bold', STEP_CLASS[step])}>
          {signedPercent(rec.change_percent, lang)}
        </span>
      </div>

      <ul className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-md bg-surface-2 px-3 py-2.5 text-xs">
        <li className="font-semibold text-fg">
          {rec.occupancy === null ? t('detail.noOccupancy') : t('detail.occupancy', { value: percent(rec.occupancy, lang) })}
        </li>
        <li className="font-semibold text-fg">{t('detail.free', { count: rec.available_units ?? 0 })}</li>
        <li className="col-span-2 text-muted">
          {t('detail.anchor', {
            price: formatMoney(rec.anchor_price, currency),
            source: t(`sources.${rec.anchor_source}`, { defaultValue: rec.anchor_source }),
          })}
          {' · '}
          {t('detail.rulesTotal', { value: signedPercent(rec.adjustment_percent, lang) })}
        </li>
      </ul>

      <div className="grid gap-2">
        <p className="eyebrow">{t('detail.why')}</p>
        {ruleReasons.length === 0 ? (
          <p className="text-sm text-muted">{t('detail.backToAnchor')}</p>
        ) : (
          <ul className="grid gap-1.5">
            {ruleReasons.map(({ reason, line }, index) => (
              <li
                key={`${reason.type}-${index}`}
                className={cn('flex items-start gap-2.5 rounded-md border border-border px-2.5 py-2', !line.applied && 'border-dashed opacity-70')}
              >
                {reason.type === 'rule' && <KindIcon kind={reason.kind} className="mt-0.5 size-4 shrink-0 text-muted" />}
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold text-fg">{line.title}</span>
                  <span className="block text-xs text-muted">{line.detail}</span>
                </span>
                <span className={cn('num shrink-0 text-[13px] font-bold', line.applied ? 'text-fg' : 'text-subtle line-through')}>
                  {line.value}
                </span>
              </li>
            ))}
          </ul>
        )}
        {limitReasons.map(({ line }, index) => (
          <p key={`limit-${index}`} className="flex items-start gap-2 rounded-md bg-info-soft px-2.5 py-2 text-xs text-info-ink">
            <ShieldCheck aria-hidden className="mt-px size-3.5 shrink-0" />
            <span>
              <span className="font-semibold">{line.title}</span>: {line.detail} <span className="num font-semibold">{line.value}</span>
            </span>
          </p>
        ))}
      </div>

      <div className="grid gap-1.5">
        <p className="eyebrow">{t('detail.explanation')}</p>
        <p className="text-[13px] leading-5 text-fg">{pick(rec.explanation, lang)}</p>
        {id && <AiExplanationBlock id={id} />}
      </div>

      {rec.apply_error && (
        <p role="alert" className="flex items-start gap-2 rounded-md bg-warning-soft px-2.5 py-2 text-xs text-warning-ink">
          <TriangleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
          {t('detail.applyError', { detail: rec.apply_error })}
        </p>
      )}

      {rec.status !== 'pending' && (rec.decided_at || rec.applied_at) && (
        <p className="text-xs text-muted">
          {rec.status === 'auto_applied'
            ? t('detail.autoApplied', { date: formatDate(rec.applied_at, 'd MMM yyyy, HH:mm', lang) })
            : t(`detail.decided.${rec.status}`, {
                who: decidedBy ?? t('detail.someone'),
                date: formatDate(rec.decided_at ?? rec.applied_at, 'd MMM yyyy, HH:mm', lang),
              })}
        </p>
      )}

      {canManage && rec.status === 'pending' && id && (
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          <Button size="sm" onClick={() => onDecide('reject', [id])} loading={pending === 'reject'} disabled={pending !== null}>
            {t('actions.reject')}
          </Button>
          <Button variant="primary" size="sm" onClick={() => onDecide('approve', [id])} loading={pending === 'approve'} disabled={pending !== null}>
            <Check aria-hidden />
            {t('actions.approve')}
          </Button>
        </div>
      )}
      {canManage && rec.status === 'approved' && id && (
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          <Button variant="primary" size="sm" onClick={() => onDecide('apply', [id])} loading={pending === 'apply'} disabled={pending !== null}>
            <RotateCcw aria-hidden />
            {t('actions.retryApply')}
          </Button>
        </div>
      )}
      <Link to="/app/rates" className="text-xs font-semibold text-accent-ink underline-offset-4 hover:underline">
        {t('detail.openGrid')}
      </Link>
    </div>
  )
}

const PROVIDER_NAMES: Record<string, string> = { gemini: 'Gemini', claude: 'Claude' }

/** "Explicar con IA": the AI puts the night's figures in plain words (on demand; the server caches it). */
function AiExplanationBlock({ id }: { id: string }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const explain = useExplain()
  const result = explain.data
  if (!result) {
    return (
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" variant="subtle" onClick={() => explain.mutate(id)} loading={explain.isPending}>
          <Sparkles aria-hidden />
          {explain.isPending ? t('detail.aiExplaining') : t('detail.aiExplain')}
        </Button>
        {explain.isError && (
          <span role="alert" className="text-xs text-danger-ink">
            {errorMessage(explain.error, t)}
          </span>
        )}
      </div>
    )
  }
  if (result.simulated) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md bg-surface-2 px-2.5 py-2 text-xs text-muted">
        <span className="flex-1">{t('detail.aiUnavailable')}</span>
        <Button size="sm" variant="ghost" onClick={() => explain.mutate(id)} loading={explain.isPending}>
          {t('detail.aiRetry')}
        </Button>
      </p>
    )
  }
  return (
    <div aria-live="polite" className="grid gap-1.5 rounded-md border border-info/25 bg-info-soft px-3 py-2.5">
      <Badge tone="info" className="bg-surface/70">
        <Bot aria-hidden />
        {t('detail.aiBadge', { provider: PROVIDER_NAMES[result.provider] ?? result.provider })}
      </Badge>
      <p className="text-[13px] leading-5 text-info-ink">{pick(result.text, lang)}</p>
    </div>
  )
}
