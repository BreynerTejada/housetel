import { BrushCleaning, ListChecks, WandSparkles } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import {
  ROOM_STATUSES,
  autoAssign,
  generateTasks,
  useBoard,
  useHkMutation,
  type BoardRoom,
  type HousekeepingBoard,
  type HousekeepingStatus,
} from '../api'
import { DaySummary } from '../components/DaySummary'
import { ReportDamageSheet } from '../components/ReportDamageSheet'
import { RoomPanel } from '../components/RoomPanel'
import { RoomTile } from '../components/RoomTile'

type StateFilter = 'all' | HousekeepingStatus
const EVERYONE = 'everyone'
const UNASSIGNED = 'unassigned'
const OPEN = new Set(['pending', 'in_progress'])

interface Filters {
  state: StateFilter
  assignee: string
  withTasks: boolean
}

function matches(room: BoardRoom, { state, assignee, withTasks }: Filters): boolean {
  if (state !== 'all' && room.housekeeping_status !== state) return false
  const open = room.tasks.filter((task) => OPEN.has(task.status))
  if (withTasks && open.length === 0) return false
  if (assignee === UNASSIGNED) return open.some((task) => task.assigned_to === null)
  if (assignee !== EVERYONE) return room.tasks.some((task) => task.assigned_to?.id === assignee)
  return true
}

/** `/app/housekeeping`: the supervision board — every room by floor, the day's progress and the team's load. */
export default function BoardPage() {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const canWork = useCan('housekeeping.work')
  const canSupervise = useCan('housekeeping.supervise')
  const canRepair = useCan('housekeeping.maintenance')
  const board = useBoard()
  const [filters, setFilters] = useState<Filters>({ state: 'all', assignee: EVERYONE, withTasks: false })
  const [openRoomId, setOpenRoomId] = useState<string | null>(null)
  const [reportRoom, setReportRoom] = useState<BoardRoom | null>(null)

  const share = useHkMutation(() => autoAssign(), {
    onSuccess: (report) => {
      if (report.assigned > 0) toast.success(t('board.assigned', { count: report.assigned }))
      else if (report.staff.length === 0 && report.unassigned > 0) toast.warning(t('board.noStaff'))
      else toast(t('board.assignedNone'))
      if (report.overloaded.length > 0) toast.warning(t('board.overloaded'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })
  const generate = useHkMutation(() => generateTasks(), {
    onSuccess: (report) =>
      report.created > 0 ? toast.success(t('board.generated', { count: report.created })) : toast(t('board.generatedNone')),
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  const rooms = useMemo(() => board.data?.floors.flatMap((floor) => floor.rooms) ?? [], [board.data])
  const openRoom = rooms.find((room) => room.id === openRoomId) ?? null

  return (
    <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6">
      <PageHeader
        className="pb-0"
        title={t('board.title')}
        description={property ? t('board.description', { date: formatDate(property.business_date, 'EEEE d MMMM', lang) }) : undefined}
        actions={
          <>
            {canWork && (
              <Button asChild variant={canSupervise ? 'ghost' : 'primary'}>
                <Link to="/app/housekeeping/mine">
                  <ListChecks aria-hidden />
                  {t('board.mine')}
                </Link>
              </Button>
            )}
            {canSupervise && (
              <>
                <Button onClick={() => generate.mutate()} loading={generate.isPending}>
                  <BrushCleaning aria-hidden />
                  {t('board.generate')}
                </Button>
                <Button variant="primary" onClick={() => share.mutate()} loading={share.isPending}>
                  <WandSparkles aria-hidden />
                  {t('board.autoAssign')}
                </Button>
              </>
            )}
          </>
        }
      />

      {board.isPending ? (
        <LoadingState variant="rows" rows={6} />
      ) : board.isError ? (
        <ErrorState error={board.error} onRetry={() => board.refetch()} />
      ) : rooms.length === 0 ? (
        <EmptyState icon={BrushCleaning} title={t('board.empty')} description={t('board.emptyHint')} />
      ) : (
        <>
          <DaySummary
            summary={board.data.summary}
            staff={board.data.staff}
            minutesPerShift={board.data.settings.minutes_per_shift}
          />
          <FiltersBar data={board.data} filters={filters} onChange={setFilters} showAssignee={canSupervise} />
          <Floors data={board.data} filters={filters} onOpen={(room) => setOpenRoomId(room.id)} onClear={() => setFilters({ state: 'all', assignee: EVERYONE, withTasks: false })} />
        </>
      )}

      <RoomPanel
        room={openRoom}
        staff={board.data?.staff ?? []}
        can={{ work: canWork, supervise: canSupervise, report: canWork || canRepair || canSupervise }}
        onOpenChange={(open) => !open && setOpenRoomId(null)}
        onReport={(room) => {
          setOpenRoomId(null)
          setReportRoom(room)
        }}
      />
      {property && (
        <ReportDamageSheet
          open={reportRoom !== null}
          onOpenChange={(open) => !open && setReportRoom(null)}
          businessDate={property.business_date}
          room={reportRoom}
          canForce={canRepair || canSupervise}
        />
      )}
    </div>
  )
}

function FiltersBar({
  data,
  filters,
  onChange,
  showAssignee,
}: {
  data: HousekeepingBoard
  filters: Filters
  onChange: (filters: Filters) => void
  showAssignee: boolean
}) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const counts = data.summary.rooms
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <div className="flex min-w-0 max-w-full items-center gap-2 overflow-x-auto">
        <span id={`${ids}-state`} className="sr-only">
          {t('board.stateFilter')}
        </span>
        <ToggleGroup
          type="single"
          aria-labelledby={`${ids}-state`}
          value={filters.state}
          onValueChange={(value) => value && onChange({ ...filters, state: value as StateFilter })}
        >
          <ToggleGroupItem value="all">
            {t('board.allStates')} <span className="num text-subtle">{counts.total}</span>
          </ToggleGroupItem>
          {ROOM_STATUSES.map((state) => (
            <ToggleGroupItem key={state} value={state} className="whitespace-nowrap">
              {t(`states.${state}`)} <span className="num text-subtle">{counts[state]}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      {showAssignee && (
        <div className="flex items-center gap-2">
          <Label htmlFor={`${ids}-assignee`} className="text-[13px] text-muted">
            {t('board.assigneeFilter')}
          </Label>
          <Select name="assignee" value={filters.assignee} onValueChange={(assignee) => onChange({ ...filters, assignee })}>
            <SelectTrigger id={`${ids}-assignee`} className="h-8 w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EVERYONE}>{t('board.everyone')}</SelectItem>
              <SelectItem value={UNASSIGNED}>{t('board.unassignedFilter')}</SelectItem>
              {data.staff.map((person) => (
                <SelectItem key={person.id} value={person.id}>
                  {person.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="flex items-center gap-2">
        <Switch
          id={`${ids}-tasks`}
          name="with_tasks"
          checked={filters.withTasks}
          onCheckedChange={(withTasks) => onChange({ ...filters, withTasks })}
        />
        <Label htmlFor={`${ids}-tasks`} className="text-[13px]">
          {t('board.withTasks')}
        </Label>
      </div>
    </div>
  )
}

function Floors({
  data,
  filters,
  onOpen,
  onClear,
}: {
  data: HousekeepingBoard
  filters: Filters
  onOpen: (room: BoardRoom) => void
  onClear: () => void
}) {
  const { t } = useTranslation('housekeeping')
  const floors = data.floors
    .map((floor) => ({ ...floor, rooms: floor.rooms.filter((room) => matches(room, filters)) }))
    .filter((floor) => floor.rooms.length > 0)

  if (floors.length === 0)
    return (
      <EmptyState
        title={t('board.noRooms')}
        action={
          <Button size="sm" onClick={onClear}>
            {t('board.clearFilters')}
          </Button>
        }
      />
    )

  return (
    <div className="grid gap-7">
      {floors.map((floor) => (
        <FloorSection key={floor.floor || 'none'} floor={floor.floor} rooms={floor.rooms} onOpen={onOpen} />
      ))}
    </div>
  )
}

function FloorSection({ floor, rooms, onOpen }: { floor: string; rooms: BoardRoom[]; onOpen: (room: BoardRoom) => void }) {
  const { t } = useTranslation('housekeeping')
  const id = useId()
  return (
    <section aria-labelledby={id} className="grid gap-3">
      <div className="flex items-baseline gap-3 border-b border-border pb-2">
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {floor ? t('board.floor', { floor }) : t('board.noFloor')}
        </h2>
        <span className="text-[13px] text-muted">{t('board.rooms', { count: rooms.length })}</span>
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2.5">
        {rooms.map((room) => (
          <li key={room.id} className="flex">
            <RoomTile room={room} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </section>
  )
}
