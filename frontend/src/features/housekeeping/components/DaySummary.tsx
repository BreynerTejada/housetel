import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { HkSummary, Housekeeper, HousekeepingStatus } from '../api'
import { formatDuration } from '../lib/time'
import { ProgressMeter } from './ProgressMeter'

const STATE_ORDER: HousekeepingStatus[] = ['dirty', 'clean', 'inspected', 'out_of_service']
const DOT: Record<HousekeepingStatus, string> = {
  clean: 'bg-room-clean',
  dirty: 'bg-room-dirty',
  inspected: 'bg-room-inspected',
  out_of_service: 'bg-room-ooo',
}

/**
 * The day at a glance: rooms per state as labeled counts (each state keeps its dot, its word and its number:
 * never color alone), the share of tasks done as a meter and the load of each housekeeper against the shift.
 */
export function DaySummary({
  summary,
  staff,
  minutesPerShift,
  className,
}: {
  summary: HkSummary
  staff: Housekeeper[]
  minutesPerShift: number
  className?: string
}) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const { rooms, tasks, minutes } = summary

  return (
    <section aria-labelledby={`${ids}-title`} className={cn('grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)]', className)}>
      <h2 id={`${ids}-title`} className="sr-only">
        {t('board.summary')}
      </h2>

      <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-[13px] font-semibold text-muted">{t('board.roomsTitle')}</p>
          <p className="text-[13px] text-muted">{t('board.occupied', { count: rooms.occupied })}</p>
        </div>
        <RoomStateCounts rooms={rooms} className="mt-3 sm:grid-cols-4 lg:grid-cols-2" />
      </div>

      <div className="grid content-start gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs">
        <p className="text-[13px] font-semibold text-muted">{t('board.tasksTitle')}</p>
        <p className="text-[17px] font-bold text-fg">{t('board.tasksDone', { done: tasks.done, count: tasks.total })}</p>
        <ProgressMeter value={tasks.done} max={tasks.total} label={t('board.tasksDoneLabel')} />
        <p className="text-[13px] text-muted">
          {t('board.workDone', { done: formatDuration(minutes.done, t), total: formatDuration(minutes.total, t) })}
        </p>
        <ul className="flex flex-wrap gap-1.5 text-[12px] font-semibold">
          {tasks.in_progress > 0 && <Pill className="bg-info-soft text-info-ink">{t('board.inProgress', { count: tasks.in_progress })}</Pill>}
          {tasks.pending > 0 && <Pill className="bg-surface-2 text-fg">{t('board.pending', { count: tasks.pending })}</Pill>}
          {tasks.unassigned > 0 && <Pill className="bg-warning-soft text-warning-ink">{t('board.unassigned', { count: tasks.unassigned })}</Pill>}
          {tasks.inspections_pending > 0 && (
            <Pill className="bg-info-soft text-info-ink">{t('board.inspections', { count: tasks.inspections_pending })}</Pill>
          )}
        </ul>
      </div>

      <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <p className="text-[13px] font-semibold text-muted">{t('board.loadTitle')}</p>
        {staff.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{t('board.noHousekeepers')}</p>
        ) : (
          <ul className="mt-3 grid gap-3">
            {staff.map((person) => (
              <LoadRow key={person.id} person={person} shift={minutesPerShift} />
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

/** Rooms per housekeeping state: dot + word + number for each state (identity never rests on color alone). */
export function RoomStateCounts({
  rooms,
  size = 'lg',
  className,
}: {
  rooms: HkSummary['rooms']
  size?: 'md' | 'lg'
  className?: string
}) {
  const { t } = useTranslation('housekeeping')
  return (
    <div className={cn('grid grid-cols-2 gap-x-4 gap-y-3', className)}>
      {STATE_ORDER.map((state) => (
        <div key={state} role="group" aria-label={t(`states.${state}`)} className="min-w-0">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-muted">
            <span aria-hidden className={cn('size-2 shrink-0 rounded-full', DOT[state])} />
            <span className="truncate">{t(`states.${state}`)}</span>
          </p>
          <p
            className={cn(
              'mt-0.5 font-semibold tracking-[-0.02em] text-fg',
              size === 'lg' ? 'text-[26px] leading-8' : 'text-xl leading-7',
            )}
          >
            {rooms[state]}
          </p>
        </div>
      ))}
    </div>
  )
}

function Pill({ className, children }: { className: string; children: string }) {
  return <li className={cn('rounded-full px-2 py-0.5', className)}>{children}</li>
}

function LoadRow({ person, shift }: { person: Housekeeper; shift: number }) {
  const { t } = useTranslation('housekeeping')
  const id = useId()
  const over = person.minutes > shift
  return (
    <li aria-labelledby={id} className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span id={id} className="truncate font-semibold text-fg">
          {person.full_name}
        </span>
        <span className={cn('shrink-0 num', over ? 'font-semibold text-warning-ink' : 'text-muted')}>
          {t('board.load', { minutes: formatDuration(person.minutes, t), shift: formatDuration(shift, t) })}
          {' · '}
          {t('board.loadTasks', { count: person.tasks })}
        </span>
      </div>
      <ProgressMeter
        size="sm"
        value={person.minutes}
        max={shift}
        tone={over ? 'warning' : 'success'}
        label={t('board.loadLabel', { name: person.full_name })}
      />
    </li>
  )
}
