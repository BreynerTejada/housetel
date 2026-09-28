import { Camera, Check, DoorOpen, Play, Plus, ThumbsDown, ThumbsUp, TriangleAlert, Users, Wrench, X } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  CLEANING_KINDS,
  PRIORITIES,
  ROOM_STATUSES,
  TASK_KINDS,
  assignTask,
  cancelTask,
  createTask,
  finishTask,
  inspectTask,
  setRoomStatus,
  startTask,
  useHkMutation,
  type BoardRoom,
  type HkTask,
  type Housekeeper,
  type HousekeepingStatus,
  type Priority,
  type TaskKind,
} from '../api'
import { formatDuration } from '../lib/time'
import { TaskBadges } from './TaskBadges'

const NOBODY = 'nobody'
const PRESSED: Record<HousekeepingStatus, string> = {
  clean: 'data-[pressed=true]:bg-room-clean-soft data-[pressed=true]:text-success-ink',
  dirty: 'data-[pressed=true]:bg-room-dirty-soft data-[pressed=true]:text-warning-ink',
  inspected: 'data-[pressed=true]:bg-room-inspected-soft data-[pressed=true]:text-info-ink',
  out_of_service: 'data-[pressed=true]:bg-room-ooo-soft data-[pressed=true]:text-stone-ink',
}

export interface PanelPermissions {
  work: boolean
  supervise: boolean
  report: boolean
}

/**
 * Everything about one room on the board: change its state, who is in it and who arrives, its block and
 * reported damage, and its tasks (assign, start / finish, inspect, cancel, create). Housekeepers only mark
 * clean / dirty and work their own tasks; supervisors do everything.
 */
export function RoomPanel({
  room,
  staff,
  can,
  onOpenChange,
  onReport,
}: {
  room: BoardRoom | null
  staff: Housekeeper[]
  can: PanelPermissions
  onOpenChange: (open: boolean) => void
  onReport: (room: BoardRoom) => void
}) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const [error, setError] = useState<string | null>(null)
  const changeState = useHkMutation(
    ({ roomId, status }: { roomId: string; status: HousekeepingStatus }) => setRoomStatus(roomId, status),
    {
      onSuccess: (data) =>
        toast.success(t('panel.stateChanged', { number: data.number, status: t(`common:status.room.${data.housekeeping_status}`) })),
      onError: (issue) => setError(errorMessage(issue, t)),
    },
  )

  if (!room) return <Sheet open={false} onOpenChange={onOpenChange} />
  const allowed = can.supervise ? ROOM_STATUSES : (['clean', 'dirty'] as HousekeepingStatus[])
  const roomType = room.room_type.name[lang] || room.room_type.name.es || room.room_type.code

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(30rem,94vw)]">
        <SheetHeader>
          <SheetTitle>{t('card.room', { number: room.number })}</SheetTitle>
          <SheetDescription>
            {roomType}
            {room.floor ? ` · ${t('card.floor', { floor: room.floor })}` : ''}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="grid content-start gap-6">
          {(can.work || can.supervise) && (
            <div className="grid gap-2">
              <p id={`state-${room.id}`} className="eyebrow">
                {t('panel.state')}
              </p>
              <div role="group" aria-labelledby={`state-${room.id}`} className="flex flex-wrap gap-1.5">
                {allowed.map((status) => {
                  const pressed = room.housekeeping_status === status
                  return (
                    <button
                      key={status}
                      type="button"
                      aria-pressed={pressed}
                      data-pressed={pressed}
                      disabled={changeState.isPending}
                      onClick={() => {
                        setError(null)
                        if (!pressed) changeState.mutate({ roomId: room.id, status })
                      }}
                      className={cn(
                        'h-9 rounded-lg border border-border px-3 text-[13px] font-semibold text-muted transition-colors hover:text-fg disabled:opacity-60',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 data-[pressed=true]:border-transparent',
                        PRESSED[status],
                      )}
                    >
                      {t(`common:status.room.${status}`)}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <Facts room={room} lang={lang} />

          {error && (
            <p role="alert" className="flex gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {error}
            </p>
          )}

          <div className="grid gap-3">
            <p className="eyebrow">{t('panel.tasks')}</p>
            {room.tasks.length === 0 ? (
              <p className="text-sm text-muted">{t('panel.noTasks')}</p>
            ) : (
              room.tasks.map((task) => <TaskRow key={task.id} task={task} staff={staff} can={can} onError={setError} />)
            )}
            {can.supervise && <NewTask room={room} staff={staff} onError={setError} />}
          </div>

          {can.report && (
            <Button variant="secondary" className="justify-self-start" onClick={() => onReport(room)}>
              <Camera aria-hidden />
              {t('panel.report')}
            </Button>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

function Fact({ icon, title, children }: { icon: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted">{icon}</span>
      <div className="min-w-0 text-sm">
        <p className="font-semibold text-fg">{title}</p>
        {children && <div className="text-[13px] text-muted">{children}</div>}
      </div>
    </div>
  )
}

function Facts({ room, lang }: { room: BoardRoom; lang: 'es' | 'en' }) {
  const { t } = useTranslation('housekeeping')
  return (
    <div className="grid gap-3">
      <p className="eyebrow">{t('panel.occupancy')}</p>
      {room.in_house ? (
        <Fact icon={<Users aria-hidden className="size-4" />} title={t('panel.inHouse', { code: room.in_house.code })}>
          {t('panel.inHouseDetail', {
            guests: t('tile.guests', { count: room.in_house.guests }),
            date: formatDate(room.in_house.checkout_date, 'EEEE d MMM', lang),
          })}
        </Fact>
      ) : (
        <p className="text-sm text-muted">{t('panel.free')}</p>
      )}
      {room.arrival_today && (
        <Fact icon={<DoorOpen aria-hidden className="size-4" />} title={t('panel.arrival', { code: room.arrival_today.code })}>
          {room.arrival_today.eta && t('panel.arrivalEta', { eta: room.arrival_today.eta })}
          {room.arrival_today.is_vip && <span className="ml-2 font-semibold text-warning-ink">{t('card.vip')}</span>}
        </Fact>
      )}
      {room.active_block && (
        <Fact icon={<X aria-hidden className="size-4" />} title={t('panel.block')}>
          {t('panel.blockUntil', { date: formatDate(room.active_block.end_date, 'd MMM', lang), reason: room.active_block.reason })}
        </Fact>
      )}
      {room.open_tickets > 0 && (
        <Fact icon={<Wrench aria-hidden className="size-4" />} title={t('panel.openTickets', { count: room.open_tickets })}>
          <Link to={`/app/maintenance?room=${room.id}`} className="font-semibold text-accent-ink hover:underline">
            {t('panel.seeTickets')}
          </Link>
        </Fact>
      )}
    </div>
  )
}

function TaskRow({
  task,
  staff,
  can,
  onError,
}: {
  task: HkTask
  staff: Housekeeper[]
  can: PanelPermissions
  onError: (message: string | null) => void
}) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const act = useHkMutation((run: () => Promise<unknown>) => run(), {
    onSuccess: () => onError(null),
    onError: (issue) => onError(errorMessage(issue, t)),
  })
  const open = task.status === 'pending' || task.status === 'in_progress'
  const inspectable = can.supervise && (task.kind === 'inspection' ? open : CLEANING_KINDS.includes(task.kind) && task.status === 'done')

  return (
    <article aria-labelledby={`${ids}-kind`} className="grid gap-3 rounded-xl border border-border p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p id={`${ids}-kind`} className="font-semibold text-fg">
          {t(`kinds.${task.kind}`)}
        </p>
        <StatusBadge kind="task" status={task.status} />
      </div>
      <TaskBadges task={task} />
      <p className="text-[13px] text-muted">
        {t('panel.estimated', { time: formatDuration(task.estimated_minutes, t) })}
        {task.finished_by && ` · ${t('panel.doneBy', { name: task.finished_by.full_name })}`}
      </p>
      {task.notes && <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] whitespace-pre-line text-fg">{task.notes}</p>}
      {open && task.waiting_for_checkout && (
        <p id={`${ids}-waiting`} className="text-[13px] font-semibold text-stone-ink">
          {t('card.waitingCheckout')}
        </p>
      )}
      {can.supervise && open && task.kind !== 'inspection' && (
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-assignee`}>{t('panel.assign')}</Label>
          <Select
            name="assigned_to"
            value={task.assigned_to?.id ?? NOBODY}
            onValueChange={(value) => act.mutate(() => assignTask(task.id, value === NOBODY ? null : value))}
            disabled={act.isPending}
          >
            <SelectTrigger id={`${ids}-assignee`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NOBODY}>{t('panel.nobody')}</SelectItem>
              {staff.map((person) => (
                <SelectItem key={person.id} value={person.id}>
                  {person.full_name}
                </SelectItem>
              ))}
              {task.assigned_to && !staff.some((person) => person.id === task.assigned_to?.id) && (
                <SelectItem value={task.assigned_to.id}>{task.assigned_to.full_name}</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {can.work && task.kind !== 'inspection' && task.status === 'pending' && (
          <Button
            size="sm"
            variant="primary"
            disabled={task.waiting_for_checkout}
            aria-describedby={task.waiting_for_checkout ? `${ids}-waiting` : undefined}
            loading={act.isPending}
            onClick={() => act.mutate(() => startTask(task.id))}
          >
            <Play aria-hidden />
            {t('panel.start')}
          </Button>
        )}
        {can.work && task.kind !== 'inspection' && task.status === 'in_progress' && (
          <Button size="sm" variant="primary" loading={act.isPending} onClick={() => act.mutate(() => finishTask(task.id))}>
            <Check aria-hidden />
            {t('panel.finish')}
          </Button>
        )}
        {inspectable && (
          <>
            <Button size="sm" variant="primary" loading={act.isPending} onClick={() => act.mutate(() => inspectTask(task.id, true))}>
              <ThumbsUp aria-hidden />
              {t('panel.approve')}
            </Button>
            <Button size="sm" disabled={act.isPending} title={t('panel.rejectHint')} onClick={() => act.mutate(() => inspectTask(task.id, false))}>
              <ThumbsDown aria-hidden />
              {t('panel.reject')}
            </Button>
          </>
        )}
        {can.supervise && open && (
          <Button
            size="sm"
            variant="ghost"
            className="text-muted"
            disabled={act.isPending}
            onClick={() => act.mutate(() => cancelTask(task.id).then(() => toast.success(t('panel.cancelled'))))}
          >
            {t('panel.cancel')}
          </Button>
        )}
      </div>
    </article>
  )
}

function NewTask({ room, staff, onError }: { room: BoardRoom; staff: Housekeeper[]; onError: (message: string | null) => void }) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<TaskKind>('deep_clean')
  const [priority, setPriority] = useState<Priority>('normal')
  const [assignee, setAssignee] = useState(NOBODY)
  const [notes, setNotes] = useState('')
  const create = useHkMutation(
    () => createTask({ room_id: room.id, kind, priority, notes: notes.trim(), assigned_to_id: assignee === NOBODY ? null : assignee }),
    {
      onSuccess: () => {
        toast.success(t('panel.created'))
        setOpen(false)
        setNotes('')
      },
      onError: (issue) => onError(errorMessage(issue, t)),
    },
  )

  if (!open)
    return (
      <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setOpen(true)}>
        <Plus aria-hidden />
        {t('panel.newTask')}
      </Button>
    )

  function submit(event: FormEvent) {
    event.preventDefault()
    onError(null)
    create.mutate(undefined)
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-dashed border-border-strong p-3.5">
      <p className="font-semibold text-fg">{t('panel.newTask')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-kind`}>{t('panel.kind')}</Label>
          <Select name="kind" value={kind} onValueChange={(value) => setKind(value as TaskKind)}>
            <SelectTrigger id={`${ids}-kind`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TASK_KINDS.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`kinds.${value}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-priority`}>{t('panel.priority')}</Label>
          <Select name="priority" value={priority} onValueChange={(value) => setPriority(value as Priority)}>
            <SelectTrigger id={`${ids}-priority`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIORITIES.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`priorities.${value}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-assignee`}>{t('panel.assign')}</Label>
        <Select name="assigned_to" value={assignee} onValueChange={setAssignee}>
          <SelectTrigger id={`${ids}-assignee`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NOBODY}>{t('panel.nobody')}</SelectItem>
            {staff.map((person) => (
              <SelectItem key={person.id} value={person.id}>
                {person.full_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-notes`}>{t('panel.notes')}</Label>
        <Textarea
          id={`${ids}-notes`}
          name="notes"
          rows={2}
          value={notes}
          placeholder={t('panel.notesPlaceholder')}
          onChange={(event) => setNotes(event.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" variant="primary" loading={create.isPending}>
          {t('panel.create')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          {t('common:actions.cancel')}
        </Button>
      </div>
    </form>
  )
}
