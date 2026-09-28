import { useMutation } from '@tanstack/react-query'
import { ExternalLink, TriangleAlert } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { confirmAction, rejectAction, type CopilotAction } from '../api'

/** Detail rows shown for each action, in reading order (internal ids are never shown). */
const ROWS: Record<string, string[]> = {
  create_reservation: ['guest', 'room_type', 'rate_plan', 'checkin', 'checkout', 'nights', 'adults', 'children', 'total'],
  move_room: ['code', 'guest', 'from_room', 'to_room', 'to_room_type', 'checkin', 'checkout'],
  check_in: ['code', 'guest', 'rooms', 'balance'],
  check_out: ['code', 'guest', 'rooms', 'balance'],
  send_message: ['code', 'guest', 'channel', 'to', 'template_code', 'message'],
  block_room: ['room', 'start', 'end', 'nights', 'kind', 'reason'],
  add_extra: ['code', 'guest', 'extra', 'quantity', 'unit_price', 'subtotal', 'tax', 'total'],
}
const MONEY = new Set(['total', 'balance', 'unit_price', 'subtotal', 'tax'])
const DATES = new Set(['checkin', 'checkout', 'start', 'end'])
const TRANSLATED = new Set(['channel', 'kind', 'template_code'])

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

/**
 * A copilot proposal as a tear-off slip: what will happen on top, the perforation, and the stub where the
 * user confirms or discards it. Once decided, the stub carries a stamp (done, discarded or failed).
 */
export function ProposalCard({ action, onDecided }: { action: CopilotAction; onDecided: (action: CopilotAction) => void }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const labelId = useId()
  const [problem, setProblem] = useState<string | null>(null)
  const decide = useMutation({
    mutationFn: (verdict: 'confirm' | 'reject') => (verdict === 'confirm' ? confirmAction(action.id) : rejectAction(action.id)),
    onMutate: () => setProblem(null),
    onSuccess: onDecided,
    onError: (error) => setProblem(errorMessage(error, t)),
  })

  const details = action.details ?? {}
  const currency = String(details.currency ?? property?.currency ?? 'COP')
  const actionLabel = t(`actions.${action.action}`, { defaultValue: t('actions.unknown') })
  const warnings = Array.isArray(details.warnings) ? (details.warnings as string[]) : []
  const rows = (ROWS[action.action] ?? [])
    .filter((key) => !isEmpty(details[key]))
    .filter((key) => key !== 'to_room_type' || details.category_change === true)
    .map((key) => ({ key, value: formatValue(key, details[key]) }))
  const reservationId = String(action.result?.reservation_id ?? details.reservation_id ?? '')

  function formatValue(key: string, value: unknown): string {
    if (MONEY.has(key)) return formatMoney(String(value), currency)
    if (DATES.has(key)) return formatDate(String(value), 'EEE d MMM', lang)
    if (TRANSLATED.has(key)) return t(`values.${String(value)}`, { defaultValue: String(value) })
    if (Array.isArray(value)) return value.join(', ')
    if (typeof value === 'boolean') return value ? t('details.yes') : t('details.no')
    return String(value)
  }

  return (
    <article
      aria-labelledby={labelId}
      className="animate-pop-in overflow-hidden rounded-lg border border-border bg-surface shadow-xs"
    >
      <div className="px-4 pt-3.5 pb-3.5">
        <p id={labelId} className="eyebrow !text-accent-ink">
          {t('proposal.eyebrow')} · {actionLabel}
        </p>
        <p className="mt-1 text-[14.5px] leading-snug font-bold text-fg">{action.summary}</p>
        {rows.length > 0 && (
          <dl className="mt-3 grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1 text-[13px]">
            {rows.map(({ key, value }) => (
              <div key={key} className="contents">
                <dt className="text-muted">{t(`details.${key}`)}</dt>
                <dd className={cn('min-w-0 font-semibold break-words text-fg', (MONEY.has(key) || key.endsWith('room')) && 'num')}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {warnings.length > 0 && (
          <div className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-[12.5px] text-warning-ink">
            <p className="flex items-center gap-1.5 font-bold">
              <TriangleAlert aria-hidden className="size-3.5" />
              {t('proposal.warnings')}
            </p>
            <ul className="mt-1 list-disc pl-5">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* The perforation: a dashed tear line with punched notches, like the stub of a hotel voucher. */}
      <div aria-hidden className="relative h-0 border-t border-dashed border-border-strong">
        <span className="absolute -top-2 -left-2 size-4 rounded-full border border-border bg-bg" />
        <span className="absolute -top-2 -right-2 size-4 rounded-full border border-border bg-bg" />
      </div>

      <div className="flex min-h-12 flex-wrap items-center gap-2 bg-surface-2/60 px-4 py-2.5">
        {action.status === 'proposed' ? (
          <>
            <Button variant="primary" size="sm" loading={decide.isPending && decide.variables === 'confirm'}
              disabled={decide.isPending} onClick={() => decide.mutate('confirm')}>
              {t('proposal.confirm')}
            </Button>
            <Button variant="ghost" size="sm" disabled={decide.isPending} onClick={() => decide.mutate('reject')}>
              {t('proposal.reject')}
            </Button>
          </>
        ) : (
          <Stamp status={action.status} />
        )}
        {action.status === 'executed' && reservationId && (
          <Button asChild variant="link" size="sm" className="ml-auto">
            <Link to={`/app/reservations/${reservationId}`}>
              {t('proposal.openReservation')}
              <ExternalLink aria-hidden className="size-3.5" />
            </Link>
          </Button>
        )}
        {action.status === 'failed' && action.error && (
          <p className="w-full text-[12.5px] text-danger-ink">{action.error}</p>
        )}
        {problem && (
          <p role="alert" className="w-full text-[12.5px] text-danger-ink">
            {problem}
          </p>
        )}
      </div>
    </article>
  )
}

const STAMP_TONE = {
  executed: 'border-success/70 text-success-ink',
  rejected: 'border-stone/70 text-stone-ink',
  failed: 'border-danger/70 text-danger-ink',
} as const

/** A rubber stamp on the stub (the desk's way of saying "done"). */
function Stamp({ status }: { status: Exclude<CopilotAction['status'], 'proposed'> }) {
  const { t } = useTranslation('ai')
  return (
    <span
      className={cn(
        'inline-flex -rotate-2 items-center rounded-sm border-2 px-2 py-0.5 text-[11px] font-extrabold tracking-[0.14em] uppercase motion-safe:animate-pop-in',
        STAMP_TONE[status],
      )}
    >
      {t(`proposal.${status}`)}
    </span>
  )
}
