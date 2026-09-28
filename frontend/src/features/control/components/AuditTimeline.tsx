import { ArrowUpRight, Building, Undo2 } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AuditEvent } from '../api'
import { actionLabel, actorName, appLabel, clockTime, dayHeading, dayKey } from '../lib/labels'
import { SourceAvatar } from './badges'
import { UndoButton } from './UndoButton'

interface Props {
  events: AuditEvent[]
  /** Opens the detail of an event (before/after). */
  onOpen: (id: string) => void
  /** The user holds `control.audit_undo`: reversible events get a "Deshacer" button. */
  canUndo: boolean
  /** Hides the "go to object" link (e.g. inside the reservation it would point to the same page). */
  hideLinks?: boolean
  selectedId?: string | null
}

/**
 * The hotel's logbook: events grouped by day, newest first, on a vertical line; each shows who (a person or a
 * machine), what happened in plain words, where it lives and — when the action can be reverted — "Deshacer".
 */
export function AuditTimeline({ events, onOpen, canUndo, hideLinks = false, selectedId }: Props) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const days = useMemo(() => {
    const groups: { key: string; events: AuditEvent[] }[] = []
    for (const event of events) {
      const key = dayKey(event.created_at)
      const last = groups[groups.length - 1]
      if (last && last.key === key) last.events.push(event)
      else groups.push({ key, events: [event] })
    }
    return groups
  }, [events])

  return (
    <div className="grid gap-5">
      {days.map((day) => (
        <section key={day.key} aria-label={dayHeading(t, lang, day.key)} className="grid gap-1">
          <h3 className="sticky top-14 z-10 -mx-1 flex items-center gap-2 bg-bg/90 px-1 py-1.5 backdrop-blur-sm">
            <span aria-hidden className="size-2.5 rounded-full border border-border-strong bg-bg" />
            <span className="text-[13px] font-bold text-fg first-letter:uppercase">{dayHeading(t, lang, day.key)}</span>
            <span className="num text-xs text-subtle">{day.events.length}</span>
          </h3>
          <ol className="relative">
            <span aria-hidden className="absolute top-2 bottom-2 left-[calc(3rem+0.75rem+0.875rem)] w-px bg-border" />
            {day.events.map((event) => (
              <TimelineItem
                key={event.id}
                event={event}
                onOpen={onOpen}
                canUndo={canUndo}
                hideLinks={hideLinks}
                selected={event.id === selectedId}
                relative={formatRelative(event.created_at, lang)}
                time={clockTime(event.created_at, lang)}
              />
            ))}
          </ol>
        </section>
      ))}
    </div>
  )
}

function TimelineItem({
  event,
  onOpen,
  canUndo,
  hideLinks,
  selected,
  relative,
  time,
}: {
  event: AuditEvent
  onOpen: (id: string) => void
  canUndo: boolean
  hideLinks: boolean
  selected: boolean
  relative: string
  time: string
}) {
  const { t, i18n } = useTranslation('control')
  const label = actionLabel(t, i18n, event.action)
  const summary = event.summary || label
  const undone = Boolean(event.undone_at)
  const showLink = !hideLinks && Boolean(event.target_link)
  const showUndo = event.undoable && canUndo

  return (
    <li
      className={cn(
        'group relative grid grid-cols-[3rem_1.75rem_minmax(0,1fr)] gap-x-3 rounded-lg py-2 pr-2 transition-colors sm:grid-cols-[3rem_1.75rem_minmax(0,1fr)_auto]',
        selected ? 'bg-accent-soft/50' : 'hover:bg-surface-2/60',
      )}
    >
      <time dateTime={event.created_at} title={relative} className="num pt-1.5 text-right text-xs text-muted">
        {time}
      </time>
      <SourceAvatar source={event.source} actor={event.actor} className="relative mt-0.5 ring-bg" />
      <div className="min-w-0">
        <button
          type="button"
          onClick={() => onOpen(event.id)}
          aria-label={t('audit.viewDetail', { summary })}
          className={cn(
            'rounded-sm text-left text-sm leading-5 break-words text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
            undone && 'text-muted line-through decoration-border-strong',
          )}
        >
          {summary}
        </button>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted">
          <span className="font-semibold text-fg/75">{actorName(event, t)}</span>
          <span aria-hidden>·</span>
          <span>{label}</span>
          <span aria-hidden className="hidden sm:inline">
            ·
          </span>
          <span className="hidden sm:inline">{appLabel(t, i18n, event.app)}</span>
          {event.scope === 'organization' && (
            <Tooltip content={t('audit.organizationEventHint')}>
              <Badge tone="neutral" tabIndex={0} className="cursor-default">
                <Building aria-hidden />
                {t('audit.organizationEvent')}
              </Badge>
            </Tooltip>
          )}
          {undone && (
            <Badge tone="stone">
              <Undo2 aria-hidden />
              {event.undone_by ? t('audit.undoneBy', { name: event.undone_by.name, when: formatRelative(event.undone_at, normalizeLang(i18n.language)) }) : t('audit.undone')}
            </Badge>
          )}
        </div>
      </div>
      {(showLink || showUndo) && (
      <div className="col-start-3 mt-1.5 flex flex-wrap items-center gap-1.5 sm:col-start-4 sm:mt-0 sm:justify-end sm:self-center">
        {showLink && (
          <Link
            to={event.target_link}
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-[13px] font-semibold text-accent-ink hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {t('audit.goToObject')}
            <ArrowUpRight aria-hidden className="size-3.5" />
          </Link>
        )}
        {showUndo && <UndoButton event={event} />}
      </div>
      )}
    </li>
  )
}
