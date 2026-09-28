import { Camera, Search, Wrench, X } from 'lucide-react'
import { useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty, useMe } from '@/lib/auth'
import { useCan } from '@/lib/permissions'
import { useDebouncedValue } from '@/features/guests/hooks'
import { useBoard, useStaff, useTickets, type MaintenanceTicket, type TicketFilters, type TicketStatus } from '../api'
import { ReportDamageSheet } from '../components/ReportDamageSheet'
import { TicketCard } from '../components/TicketCard'
import { TicketPanel } from '../components/TicketPanel'

type View = 'pending' | 'resolved' | 'all'
const STATUSES: Record<View, TicketStatus[] | undefined> = {
  pending: ['open', 'in_progress'],
  resolved: ['resolved'],
  all: undefined,
}

/** `/app/maintenance`: reported damage by status, the rooms it keeps out of service, and the repair work. */
export default function MaintenancePage() {
  const { t } = useTranslation('housekeeping')
  const { property } = useActiveProperty()
  const me = useMe().data
  const canWork = useCan('housekeeping.work')
  const canRepair = useCan('housekeeping.maintenance')
  const canSupervise = useCan('housekeeping.supervise')
  const mayRepair = canRepair || canSupervise
  const mayReport = canWork || mayRepair
  const [params, setParams] = useSearchParams()
  const roomId = params.get('room') ?? undefined
  const [view, setView] = useState<View>('pending')
  const [search, setSearch] = useState('')
  const [blocking, setBlocking] = useState(false)
  const [mine, setMine] = useState(false)
  const [reporting, setReporting] = useState(params.get('new') === '1')
  const [openId, setOpenId] = useState<string | null>(null)
  const q = useDebouncedValue(search, 300)

  const filters: TicketFilters = { status: STATUSES[view], blocking, mine, q, room: roomId }
  const tickets = useTickets(filters)
  const board = useBoard()
  const staff = useStaff(mayRepair)
  const rooms = useMemo(() => board.data?.floors.flatMap((floor) => floor.rooms) ?? [], [board.data])
  const filterRoom = rooms.find((room) => room.id === roomId)
  const list = tickets.data ?? []
  const openTicket = list.find((ticket) => ticket.id === openId) ?? null

  useEffect(() => {
    if (params.get('new') !== '1') return
    const next = new URLSearchParams(params)
    next.delete('new')
    setParams(next, { replace: true })
  }, [params, setParams])

  function clearRoom() {
    const next = new URLSearchParams(params)
    next.delete('room')
    setParams(next)
  }

  const cards = (items: MaintenanceTicket[]) => items.map((ticket) => <TicketCard key={ticket.id} ticket={ticket} onOpen={(item) => setOpenId(item.id)} />)

  return (
    <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-6">
      <PageHeader
        className="pb-0"
        title={t('maintenance.title')}
        description={t('maintenance.description')}
        actions={
          mayReport && (
            <Button variant="primary" onClick={() => setReporting(true)}>
              <Camera aria-hidden />
              {t('maintenance.report')}
            </Button>
          )
        }
      />

      <Toolbar
        view={view}
        onView={setView}
        search={search}
        onSearch={setSearch}
        blocking={blocking}
        onBlocking={setBlocking}
        mine={mine}
        onMine={setMine}
      />
      {roomId && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="rounded-full bg-surface-2 px-2.5 py-1 font-semibold text-fg">
            {t('maintenance.roomFilter', { number: filterRoom?.number ?? '…' })}
          </span>
          <Button variant="ghost" size="sm" onClick={clearRoom}>
            <X aria-hidden />
            {t('maintenance.allRooms')}
          </Button>
        </p>
      )}

      {tickets.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : tickets.isError ? (
        <ErrorState error={tickets.error} onRetry={() => tickets.refetch()} />
      ) : view === 'pending' ? (
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <Column title={t('maintenance.open')} count={list.filter((ticket) => ticket.status === 'open').length} empty={t('maintenance.emptyOpen')}>
            {cards(list.filter((ticket) => ticket.status === 'open'))}
          </Column>
          <Column
            title={t('maintenance.inProgress')}
            count={list.filter((ticket) => ticket.status === 'in_progress').length}
            empty={t('maintenance.emptyProgress')}
          >
            {cards(list.filter((ticket) => ticket.status === 'in_progress'))}
          </Column>
        </div>
      ) : list.length === 0 ? (
        <EmptyState icon={Wrench} title={t('maintenance.emptyList')} />
      ) : (
        <Column title={t(view === 'resolved' ? 'maintenance.resolved' : 'maintenance.list')} count={list.length} empty="">
          <div className="grid gap-3 md:grid-cols-2">{cards(list)}</div>
        </Column>
      )}

      <TicketPanel
        ticket={openTicket}
        onOpenChange={(open) => !open && setOpenId(null)}
        can={{ repair: mayRepair, supervise: canSupervise }}
        technicians={staff.data?.maintenance ?? []}
        businessDate={property?.business_date ?? ''}
        userId={me?.id}
      />
      {property && (
        <ReportDamageSheet
          open={reporting && mayReport}
          onOpenChange={setReporting}
          businessDate={property.business_date}
          rooms={rooms}
          technicians={mayRepair ? staff.data?.maintenance : undefined}
          canForce={mayRepair}
        />
      )}
    </div>
  )
}

function Toolbar({
  view,
  onView,
  search,
  onSearch,
  blocking,
  onBlocking,
  mine,
  onMine,
}: {
  view: View
  onView: (view: View) => void
  search: string
  onSearch: (value: string) => void
  blocking: boolean
  onBlocking: (value: boolean) => void
  mine: boolean
  onMine: (value: boolean) => void
}) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <span id={`${ids}-view`} className="sr-only">
        {t('maintenance.view')}
      </span>
      <ToggleGroup type="single" aria-labelledby={`${ids}-view`} value={view} onValueChange={(value) => value && onView(value as View)}>
        <ToggleGroupItem value="pending">{t('maintenance.pending')}</ToggleGroupItem>
        <ToggleGroupItem value="resolved">{t('maintenance.resolved')}</ToggleGroupItem>
        <ToggleGroupItem value="all">{t('maintenance.all')}</ToggleGroupItem>
      </ToggleGroup>
      <div className="relative w-full min-w-0 sm:w-auto sm:max-w-xs sm:flex-1">
        <Label htmlFor={`${ids}-search`} className="sr-only">
          {t('maintenance.search')}
        </Label>
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-subtle" />
        <Input
          id={`${ids}-search`}
          name="q"
          type="search"
          value={search}
          placeholder={t('maintenance.searchPlaceholder')}
          onChange={(event) => onSearch(event.target.value)}
          className="pl-8"
        />
      </div>
      <div className="flex items-center gap-2">
        <Switch id={`${ids}-blocking`} name="blocking" checked={blocking} onCheckedChange={onBlocking} />
        <Label htmlFor={`${ids}-blocking`} className="text-[13px]">
          {t('maintenance.blocking')}
        </Label>
      </div>
      <div className="flex items-center gap-2">
        <Switch id={`${ids}-mine`} name="mine" checked={mine} onCheckedChange={onMine} />
        <Label htmlFor={`${ids}-mine`} className="text-[13px]">
          {t('maintenance.mine')}
        </Label>
      </div>
    </div>
  )
}

function Column({ title, count, empty, children }: { title: string; count: number; empty: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="grid content-start gap-3">
      <div className="flex items-baseline gap-2 border-b border-border pb-2">
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {title}
        </h2>
        <span className="text-[13px] text-muted num">{count}</span>
      </div>
      {count === 0 && empty ? <p className="py-4 text-sm text-muted">{empty}</p> : children}
    </section>
  )
}
