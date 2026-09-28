import { ArrowRight, ArrowUpRight, Building, CircleSlash, Lock, Undo2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useAuditEvent, type AuditEventDetail } from '../api'
import { actionLabel, actorName, appLabel, fieldLabel, valueLabel } from '../lib/labels'
import { SourceAvatar } from './badges'
import { UndoButton } from './UndoButton'

interface Props {
  eventId: string | null
  onOpenChange: (open: boolean) => void
  /** Navigates between an action and the one that undid it (or the original of an undo). */
  onNavigate: (id: string) => void
  hideLinks?: boolean
}

/** The detail of one audit event: who, when, what exactly changed (before → after) and, when possible, undo. */
export function AuditEventSheet({ eventId, onOpenChange, onNavigate, hideLinks = false }: Props) {
  const { t } = useTranslation('control')
  return (
    <Sheet open={eventId !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[min(36rem,100vw)]">
        {eventId ? (
          <EventDetail id={eventId} onNavigate={onNavigate} hideLinks={hideLinks} />
        ) : (
          <SheetHeader>
            <SheetTitle>{t('audit.detail.title')}</SheetTitle>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  )
}

function EventDetail({ id, onNavigate, hideLinks }: { id: string; onNavigate: (id: string) => void; hideLinks: boolean }) {
  const { t } = useTranslation('control')
  const query = useAuditEvent(id)
  if (query.isPending) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>{t('audit.detail.title')}</SheetTitle>
          <SheetDescription className="sr-only">{t('audit.detail.title')}</SheetDescription>
        </SheetHeader>
        <LoadingState variant="rows" rows={6} />
      </>
    )
  }
  if (query.isError) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>{t('audit.detail.title')}</SheetTitle>
          <SheetDescription className="sr-only">{t('audit.detail.title')}</SheetDescription>
        </SheetHeader>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </>
    )
  }
  return <EventBody event={query.data} onNavigate={onNavigate} hideLinks={hideLinks} />
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 py-2 text-[13px] sm:grid-cols-[8rem_minmax(0,1fr)]">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-fg">{children}</dd>
    </div>
  )
}

function EventBody({ event, onNavigate, hideLinks }: { event: AuditEventDetail; onNavigate: (id: string) => void; hideLinks: boolean }) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const canUndoPermission = useCan('control.audit_undo')
  const label = actionLabel(t, i18n, event.action)
  const whenPattern = lang === 'en' ? "EEEE, MMMM d, yyyy 'at' HH:mm:ss" : "EEEE d 'de' MMMM 'de' yyyy, HH:mm:ss"
  const hasChanges = event.diff.length > 0 || event.details.length > 0 || event.row_changes.length > 0

  return (
    <>
      <SheetHeader>
        <SheetTitle className="break-words">{event.summary || label}</SheetTitle>
        <SheetDescription>
          {label} · {appLabel(t, i18n, event.app)}
        </SheetDescription>
      </SheetHeader>

      <SheetBody className="grid grid-cols-1 content-start gap-6">
        <dl className="divide-y divide-border rounded-lg border border-border px-3">
          <Fact label={t('audit.detail.when')}>
            <span className="first-letter:uppercase">{formatDate(event.created_at, whenPattern, lang)}</span>
          </Fact>
          <Fact label={t('audit.detail.who')}>
            <span className="flex items-center gap-2">
              <SourceAvatar source={event.source} actor={event.actor} className="size-6 ring-0" />
              <span className="min-w-0">
                <span className="font-semibold">{actorName(event, t)}</span>
                {event.actor && <span className="block text-xs text-muted">{event.actor.email}</span>}
              </span>
            </span>
          </Fact>
          <Fact label={t('audit.detail.source')}>{t(`sources.${event.source}`)}</Fact>
          <Fact label={t('audit.detail.action')}>
            {label} <code className="ml-1 rounded bg-surface-2 px-1 py-0.5 text-[11px] text-muted">{event.action}</code>
          </Fact>
          {(event.target_type || event.scope === 'organization') && (
            <Fact label={t('audit.detail.object')}>
              <span className="flex flex-wrap items-center gap-2">
                {event.target_type && <code className="rounded bg-surface-2 px-1 py-0.5 text-[11px] text-muted">{event.target_type}</code>}
                {event.scope === 'organization' && (
                  <Badge tone="neutral">
                    <Building aria-hidden />
                    {t('audit.organizationEvent')}
                  </Badge>
                )}
                {!hideLinks && event.target_link && (
                  <Link to={event.target_link} className="inline-flex items-center gap-1 font-semibold text-accent-ink hover:underline">
                    {t('audit.goToObject')}
                    <ArrowUpRight aria-hidden className="size-3.5" />
                  </Link>
                )}
              </span>
            </Fact>
          )}
        </dl>

        <UndoPanel event={event} canUndoPermission={canUndoPermission} onNavigate={onNavigate} />

        <section className="grid gap-3" aria-labelledby="audit-detail-changes">
          <h3 id="audit-detail-changes" className="eyebrow">
            {t('audit.detail.changes')}
          </h3>
          {!hasChanges && <p className="text-sm text-muted">{t('audit.detail.noChanges')}</p>}
          {event.diff.length > 0 && <DiffTable rows={event.diff} />}
          {event.details.length > 0 && (
            <dl className="divide-y divide-border rounded-lg border border-border px-3">
              {event.details.map((row) => (
                <Fact key={row.field} label={fieldLabel(t, i18n, row.field)}>
                  <ValueText field={row.field} value={row.value} />
                </Fact>
              ))}
            </dl>
          )}
          {event.row_changes.length > 0 && (
            <div className="grid gap-2">
              <h4 className="text-[13px] font-semibold text-fg">{t('audit.detail.rows')}</h4>
              <ul className="grid gap-2">
                {event.row_changes.map((row, index) => (
                  <li key={`${row.label}-${index}`} className="rounded-lg border border-border p-2.5">
                    <p className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold text-fg">
                      <span className="num">{/^\d{4}-\d{2}-\d{2}$/.test(row.label) ? formatDate(row.label, undefined, lang) : row.label}</span>
                      {row.created && <Badge tone="info">{t('audit.detail.newRow')}</Badge>}
                    </p>
                    <DiffTable rows={row.changes} compact />
                  </li>
                ))}
              </ul>
              {event.row_changes_total > event.row_changes.length && (
                <p className="text-xs text-muted">
                  {t('audit.detail.rowsShown', { shown: event.row_changes.length, total: event.row_changes_total })}
                </p>
              )}
            </div>
          )}
        </section>

        {event.request_id && (
          <p className="text-2xs text-subtle">
            {t('audit.detail.requestId')}: <span className="num">{event.request_id}</span>
          </p>
        )}
      </SheetBody>
    </>
  )
}

function UndoPanel({ event, canUndoPermission, onNavigate }: { event: AuditEventDetail; canUndoPermission: boolean; onNavigate: (id: string) => void }) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)

  if (event.original_event_id) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-info/25 bg-info-soft/60 px-3 py-2.5 text-[13px] text-info-ink">
        <span className="flex items-center gap-2">
          <Undo2 aria-hidden className="size-4" />
          {t('audit.detail.original')}
        </span>
        <Button size="sm" variant="ghost" onClick={() => onNavigate(event.original_event_id as string)}>
          {t('audit.detail.viewOriginal')}
          <ArrowRight aria-hidden />
        </Button>
      </div>
    )
  }
  if (event.undone_at) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-stone-soft px-3 py-2.5 text-[13px] text-stone-ink">
        <span className="flex items-center gap-2">
          <Undo2 aria-hidden className="size-4" />
          {t('audit.detail.undoneBy', {
            name: event.undone_by?.name ?? t('common.system'),
            when: formatDate(event.undone_at, lang === 'en' ? 'MMM d, yyyy HH:mm' : "d MMM yyyy, HH:mm", lang),
          })}
        </span>
        {event.undo_event_id && (
          <Button size="sm" variant="ghost" onClick={() => onNavigate(event.undo_event_id as string)}>
            {t('audit.detail.undoEvent')}
            <ArrowRight aria-hidden />
          </Button>
        )}
      </div>
    )
  }
  if (event.undoable) {
    return canUndoPermission ? (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2.5">
        <p className="min-w-0 flex-1 text-[13px] text-fg/85">{t('audit.detail.canUndo')}</p>
        <UndoButton event={event} variant="primary" />
      </div>
    ) : (
      <p className="flex items-center gap-2 rounded-lg border border-border bg-surface-2/60 px-3 py-2.5 text-[13px] text-muted">
        <Lock aria-hidden className="size-4 shrink-0" />
        {t('audit.detail.noPermission')}
      </p>
    )
  }
  return (
    <p className="flex items-center gap-2 text-xs text-subtle">
      <CircleSlash aria-hidden className="size-3.5" />
      {t('audit.detail.cannotUndo')}
    </p>
  )
}

function ValueText({ field, value }: { field: string; value: unknown }) {
  const { t, i18n } = useTranslation('control')
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return <pre className="num max-h-48 overflow-auto rounded bg-surface-2 p-2 text-[11px] leading-4 whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>
  }
  return <span className="num">{valueLabel(t, i18n, field, value)}</span>
}

function DiffTable({ rows, compact = false }: { rows: { field: string; before: unknown; after: unknown }[]; compact?: boolean }) {
  const { t, i18n } = useTranslation('control')
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[20rem] text-left text-[13px]">
        {!compact && (
          <thead className="bg-surface-2/70 text-xs text-muted">
            <tr>
              <th scope="col" className="px-3 py-2 font-semibold">
                {t('audit.detail.field')}
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                {t('audit.detail.before')}
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                {t('audit.detail.after')}
              </th>
            </tr>
          </thead>
        )}
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.field} className="align-top">
              <th scope="row" className="w-[34%] px-3 py-2 font-semibold text-fg/85">
                {fieldLabel(t, i18n, row.field)}
              </th>
              <td className="px-3 py-2">
                <ValueCell field={row.field} value={row.before} tone="before" />
              </td>
              <td className="px-3 py-2">
                <ValueCell field={row.field} value={row.after} tone="after" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

/** Before values read as removed (struck, clay) and after values as added (sage); empty sides stay quiet. */
function ValueCell({ field, value, tone }: { field: string; value: unknown; tone: 'before' | 'after' }) {
  const { t, i18n } = useTranslation('control')
  const text = valueLabel(t, i18n, field, value)
  const short = text.length > 160 ? `${text.slice(0, 157)}…` : text
  if (isEmpty(value)) return <span className="text-subtle">{short}</span>
  return (
    <span
      className={
        tone === 'before'
          ? 'num rounded bg-danger-soft/60 px-1 py-0.5 break-words text-danger-ink line-through decoration-danger/40'
          : 'num rounded bg-success-soft/70 px-1 py-0.5 break-words text-success-ink'
      }
    >
      {short}
    </span>
  )
}
