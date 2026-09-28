import { Camera, Check, MessageSquareText, Play, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { HkTask } from '../api'
import { formatClock, formatDuration } from '../lib/time'
import { MinutesTag, TaskBadges } from './TaskBadges'

type Stage = 'pending' | 'waiting' | 'in_progress' | 'done'

/** Band of the hanger: sand = please clean, stone hatch = not yet (guest inside), slate = in progress. */
const BAND: Record<Stage, string> = {
  pending: 'bg-warning-soft text-warning-ink',
  waiting: 'bg-stone-soft text-stone-ink hatch',
  in_progress: 'bg-info-soft text-info-ink',
  done: 'bg-success-soft text-success-ink',
}

function stageOf(task: HkTask): Stage {
  if (task.status === 'in_progress') return 'in_progress'
  if (task.status === 'done' || task.status === 'inspected') return 'done'
  return task.waiting_for_checkout ? 'waiting' : 'pending'
}

/**
 * A task drawn as the door hanger housekeepers hang on the handle: the punched hole and its slit at the top,
 * the room number printed large, and one big button for the next step (thumb-sized on a phone).
 */
export function DoorHangerCard({
  task,
  busy = false,
  canSupervise = false,
  onStart,
  onFinish,
  onInspect,
  onReport,
}: {
  task: HkTask
  busy?: boolean
  canSupervise?: boolean
  onStart: (task: HkTask) => void
  onFinish: (task: HkTask, notes: string) => void
  onInspect: (task: HkTask, passed: boolean) => void
  onReport: (task: HkTask) => void
}) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const [note, setNote] = useState('')
  const stage = stageOf(task)
  const room = task.room
  const roomType = room.room_type.name[lang] || room.room_type.name.es || room.room_type.code
  const inspection = task.kind === 'inspection'

  let actions: ReactNode
  if (inspection) {
    actions = canSupervise ? (
      <div className="grid grid-cols-2 gap-2">
        <Button variant="primary" className="h-14 rounded-xl text-base" loading={busy} onClick={() => onInspect(task, true)}>
          <ThumbsUp aria-hidden className="size-5" />
          {t('card.approve')}
        </Button>
        <Button className="h-14 rounded-xl text-base" disabled={busy} onClick={() => onInspect(task, false)}>
          <ThumbsDown aria-hidden className="size-5" />
          {t('card.reject')}
        </Button>
      </div>
    ) : null
  } else if (stage === 'in_progress') {
    actions = (
      <>
        <div className="grid gap-1.5">
          <label htmlFor={`${ids}-note`} className="text-[13px] font-semibold text-muted">
            {t('card.note')}
          </label>
          <Textarea
            id={`${ids}-note`}
            name="notes"
            rows={2}
            value={note}
            placeholder={t('card.notePlaceholder')}
            onChange={(event) => setNote(event.target.value)}
            className="min-h-11 text-[15px]"
          />
        </div>
        <Button variant="primary" className="h-14 rounded-xl text-base" loading={busy} onClick={() => onFinish(task, note.trim())}>
          <Check aria-hidden className="size-5" />
          {t('card.finish')}
        </Button>
      </>
    )
  } else {
    actions = (
      <Button
        variant="primary"
        className="h-14 rounded-xl text-base"
        loading={busy}
        disabled={stage === 'waiting'}
        aria-describedby={stage === 'waiting' ? `${ids}-waiting` : undefined}
        onClick={() => onStart(task)}
      >
        <Play aria-hidden className="size-5" />
        {t('card.start')}
      </Button>
    )
  }

  return (
    <article
      aria-label={t('card.room', { number: room.number })}
      className="animate-pop-in overflow-hidden rounded-[22px] border border-border bg-surface shadow-sm"
    >
      <div className={cn('relative flex h-14 items-center justify-between px-5', BAND[stage])}>
        <span className="text-[11px] font-bold tracking-[0.08em] uppercase">{t(`card.stage.${stage}`)}</span>
        {/* The punched hole of the hanger and the slit that lets it slide onto the door handle. */}
        <span aria-hidden className="absolute top-0 left-1/2 h-5 w-[3px] -translate-x-1/2 bg-bg" />
        <span
          aria-hidden
          className="absolute top-3.5 left-1/2 size-7 -translate-x-1/2 rounded-full bg-bg shadow-[inset_0_1px_3px_rgb(0_0_0/0.22)] ring-1 ring-border"
        />
        <MinutesTag>{formatDuration(task.estimated_minutes, t)}</MinutesTag>
      </div>
      <div className="grid gap-4 px-5 pt-4 pb-5">
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-[44px] leading-[0.95] font-extrabold tracking-[-0.045em] text-fg">
              <span className="sr-only">{t('card.room', { number: room.number })}</span>
              <span aria-hidden>{room.number}</span>
            </h3>
            <p className="mt-1.5 truncate text-sm text-muted">
              {roomType}
              {room.floor ? ` · ${t('card.floor', { floor: room.floor })}` : ''}
            </p>
          </div>
          <p className="shrink-0 pb-1 text-right text-[15px] font-bold text-fg">{t(`kinds.${task.kind}`)}</p>
        </div>
        <TaskBadges task={task} />
        {task.notes && (
          <p className="flex gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm text-fg">
            <MessageSquareText aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
            <span className="whitespace-pre-line">{task.notes}</span>
          </p>
        )}
        {stage === 'waiting' && (
          <p id={`${ids}-waiting`} className="text-sm font-semibold text-stone-ink">
            {t('card.waitingCheckout')}
          </p>
        )}
        {stage === 'in_progress' && task.started_at && (
          <p className="text-[13px] text-muted">{t('card.startedAt', { time: formatClock(task.started_at, lang) })}</p>
        )}
        <div className="grid gap-2">
          {actions}
          <Button variant="ghost" className="h-12 rounded-xl text-[15px] text-muted" onClick={() => onReport(task)}>
            <Camera aria-hidden className="size-5" />
            {t('card.report')}
          </Button>
        </div>
      </div>
    </article>
  )
}
