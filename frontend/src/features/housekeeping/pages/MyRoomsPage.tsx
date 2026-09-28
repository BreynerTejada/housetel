import { BrushCleaning, CircleCheck, RefreshCw, TriangleAlert } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { finishTask, inspectTask, startTask, useHkMutation, useMyTasks, type HkTask } from '../api'
import { DoorHangerCard } from '../components/DoorHangerCard'
import { ProgressMeter } from '../components/ProgressMeter'
import { ReportDamageSheet } from '../components/ReportDamageSheet'
import { formatClock, formatDuration } from '../lib/time'

type Action = { kind: 'start' } | { kind: 'finish'; notes: string } | { kind: 'inspect'; passed: boolean }

function groupTasks(tasks: HkTask[]) {
  const visible = tasks.filter((task) => task.status !== 'cancelled')
  const done = visible.filter((task) => task.status === 'done' || task.status === 'inspected')
  const open = visible.filter((task) => task.status === 'pending' || task.status === 'in_progress')
  return {
    total: visible.length,
    current: open.filter((task) => task.status === 'in_progress'),
    // What can be cleaned now first; departures still waiting for their check-out after them.
    next: [
      ...open.filter((task) => task.status === 'pending' && !task.waiting_for_checkout),
      ...open.filter((task) => task.status === 'pending' && task.waiting_for_checkout),
    ],
    done,
    minutesLeft: open.reduce((sum, task) => sum + task.estimated_minutes, 0),
  }
}

/** `/app/housekeeping/mine`: the housekeeper's day on the phone — one card per room, one tap per step. */
export default function MyRoomsPage() {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const canSupervise = useCan('housekeeping.supervise')
  const canRepair = useCan('housekeeping.maintenance')
  const tasks = useMyTasks()
  const [reporting, setReporting] = useState<HkTask | null>(null)
  const [failed, setFailed] = useState<{ taskId: string; message: string } | null>(null)
  const groups = useMemo(() => groupTasks(tasks.data ?? []), [tasks.data])

  const act = useHkMutation(
    ({ task, action }: { task: HkTask; action: Action }) => {
      if (action.kind === 'start') return startTask(task.id)
      if (action.kind === 'finish') return finishTask(task.id, action.notes)
      return inspectTask(task.id, action.passed)
    },
    { onSuccess: () => setFailed(null) },
  )
  const busyId = act.isPending ? act.variables?.task.id : undefined

  function run(task: HkTask, action: Action) {
    setFailed(null)
    act.mutate({ task, action }, { onError: (error) => setFailed({ taskId: task.id, message: errorMessage(error, t) }) })
  }

  const renderCard = (task: HkTask) => (
    <div key={task.id} className="grid gap-2">
      <DoorHangerCard
        task={task}
        busy={busyId === task.id}
        canSupervise={canSupervise}
        onStart={(item) => run(item, { kind: 'start' })}
        onFinish={(item, notes) => run(item, { kind: 'finish', notes })}
        onInspect={(item, passed) => run(item, { kind: 'inspect', passed })}
        onReport={setReporting}
      />
      {failed?.taskId === task.id && (
        <p role="alert" className="flex gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {failed.message}
        </p>
      )}
    </div>
  )

  return (
    <div className="mx-auto grid w-full max-w-xl grid-cols-1 gap-7 pb-10">
      <header className="grid gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {property && <p className="eyebrow first-letter:uppercase">{formatDate(property.business_date, 'EEEE d MMMM', lang)}</p>}
            <h1 className="mt-1 text-[26px] leading-8 tracking-[-0.03em] text-fg">{t('mine.title')}</h1>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('mine.refresh')}
            onClick={() => tasks.refetch()}
            disabled={tasks.isFetching}
          >
            <RefreshCw aria-hidden className={tasks.isFetching ? 'animate-spin' : undefined} />
          </Button>
        </div>
        {groups.total > 0 && (
          <div className="grid gap-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="text-[17px] font-bold text-fg">
                {t('mine.progress', { done: groups.done.length, count: groups.total })}
              </p>
              <p className="text-sm text-muted">
                {groups.minutesLeft > 0
                  ? t('mine.left', { time: formatDuration(groups.minutesLeft, t) })
                  : t('mine.allDone')}
              </p>
            </div>
            <ProgressMeter value={groups.done.length} max={groups.total} label={t('mine.progressLabel')} />
          </div>
        )}
      </header>

      {tasks.isPending ? (
        <LoadingState variant="rows" rows={3} />
      ) : tasks.isError ? (
        <ErrorState error={tasks.error} onRetry={() => tasks.refetch()} />
      ) : groups.total === 0 ? (
        <EmptyState icon={BrushCleaning} title={t('mine.empty')} description={t('mine.emptyHint')} />
      ) : (
        <>
          {groups.current.length > 0 && <Group title={t('mine.current')}>{groups.current.map(renderCard)}</Group>}
          {groups.next.length > 0 && (
            <Group title={t('mine.next')} count={groups.next.length}>
              {groups.next.map(renderCard)}
            </Group>
          )}
          {groups.done.length > 0 && (
            <Group title={t('mine.done')} count={groups.done.length}>
              <ul className="grid divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
                {groups.done.map((task) => (
                  <li key={task.id} className="flex items-center gap-3 px-4 py-3">
                    <RoomKeyTag number={task.room.number} status={task.room.housekeeping_status} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-fg">{t(`kinds.${task.kind}`)}</p>
                      {task.finished_at && (
                        <p className="text-[13px] text-muted">{t('mine.finishedAt', { time: formatClock(task.finished_at, lang) })}</p>
                      )}
                    </div>
                    {task.status === 'inspected' ? (
                      <Badge tone="info">{t('mine.inspected')}</Badge>
                    ) : (
                      <CircleCheck aria-hidden className="size-5 text-success" />
                    )}
                  </li>
                ))}
              </ul>
            </Group>
          )}
        </>
      )}

      {property && (
        <ReportDamageSheet
          open={reporting !== null}
          onOpenChange={(open) => !open && setReporting(null)}
          businessDate={property.business_date}
          room={reporting?.room ?? null}
          canForce={canRepair || canSupervise}
        />
      )}
    </div>
  )
}

function Group({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="grid gap-3">
      <h2 id={id} className="eyebrow flex items-center gap-2">
        {title}
        {count !== undefined && <span className="rounded-full bg-surface-3 px-1.5 py-px text-[11px] text-fg num">{count}</span>}
      </h2>
      {children}
    </section>
  )
}
