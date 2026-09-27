import { Ban, ChevronRight, DoorOpen, Layers, Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useActiveMembership } from '@/lib/auth'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { HOUSEKEEPING_STATUSES, useCustomFields, useRooms, useRoomTypes, type Room, type RoomType } from '../api'
import { BulkCreateDialog } from '../components/BulkCreateDialog'
import { BulkEditSheet } from '../components/BulkEditSheet'
import { CategoryChip } from '../components/CategoryChip'
import { CreateRoomDialog } from '../components/CreateRoomDialog'
import { RoomKeyTag } from '../components/RoomKeyTag'
import { RoomStatusBadge } from '../components/RoomStatusBadge'
import { bedsSummary, sizeLabel } from '../lib/attributes'
import { naturalCompare, tr } from '../lib/text'

const ALL = 'all'

/** The hotel's room rack by category: filter, select many, edit many, open one to see its inheritance. */
export default function RoomsPage() {
  const { t, i18n } = useTranslation('inventory')
  const navigate = useNavigate()
  const membership = useActiveMembership()
  const canManage = useCan('inventory.manage') && membership !== null
  const rooms = useRooms()
  const roomTypes = useRoomTypes()
  const definitions = useCustomFields()
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(ALL)
  const [floorFilter, setFloorFilter] = useState(ALL)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkCreate, setBulkCreate] = useState(false)
  const [bulkEdit, setBulkEdit] = useState(false)
  const [createOne, setCreateOne] = useState(false)

  const allRooms = useMemo(() => rooms.data ?? [], [rooms.data])
  const types = useMemo(() => [...(roomTypes.data ?? [])].sort((a, b) => a.sort_order - b.sort_order || naturalCompare(a.code, b.code)), [roomTypes.data])
  const floors = useMemo(() => [...new Set(allRooms.map((room) => room.floor).filter(Boolean))].sort(naturalCompare), [allRooms])
  // the category filter lives in the address (`?room_type=`): a category editor links to its rooms
  const requestedType = searchParams.get('room_type')
  const typeFilter = requestedType && types.some((type) => type.id === requestedType) ? requestedType : ALL
  function setTypeFilter(value: string) {
    setSearchParams(
      (params) => {
        const next = new URLSearchParams(params)
        if (value === ALL) next.delete('room_type')
        else next.set('room_type', value)
        return next
      },
      { replace: true },
    )
  }

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    return allRooms.filter((room) => {
      if (typeFilter !== ALL && room.room_type !== typeFilter) return false
      if (floorFilter !== ALL && room.floor !== floorFilter) return false
      if (statusFilter === 'inactive') {
        if (room.is_active) return false
      } else if (statusFilter === 'blocked') {
        if (!room.active_block) return false
      } else if (statusFilter !== ALL && room.housekeeping_status !== statusFilter) return false
      if (query && !`${room.number} ${room.name}`.toLowerCase().includes(query)) return false
      return true
    })
  }, [allRooms, search, typeFilter, floorFilter, statusFilter])

  const groups = types
    .map((type) => ({ type, rooms: visible.filter((room) => room.room_type === type.id).sort((a, b) => naturalCompare(a.number, b.number)) }))
    .filter((group) => group.rooms.length > 0)
  const selectedRooms = allRooms.filter((room) => selected.has(room.id))
  const units = types.filter((type) => type.is_active).reduce((sum, type) => sum + type.units_count, 0)

  function toggle(ids: string[], on: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })
  }

  const actions = canManage && types.length > 0 && (
    <>
      <Button onClick={() => setBulkCreate(true)}>
        <Layers aria-hidden />
        {t('rooms.bulkCreate')}
      </Button>
      <Button variant="primary" onClick={() => setCreateOne(true)}>
        <Plus aria-hidden />
        {t('rooms.new')}
      </Button>
    </>
  )

  return (
    <>
      <PageHeader
        title={t('nav.rooms')}
        description={rooms.data ? t('rooms.description', { rooms: allRooms.length, units }) : t('nav.roomsHint')}
        actions={actions}
      />

      {rooms.isError || roomTypes.isError ? (
        <ErrorState
          error={rooms.error ?? roomTypes.error}
          onRetry={() => {
            if (rooms.isError) void rooms.refetch()
            if (roomTypes.isError) void roomTypes.refetch()
          }}
        />
      ) : !rooms.data || !roomTypes.data ? (
        <LoadingState variant="rows" rows={8} />
      ) : types.length === 0 ? (
        <EmptyState
          icon={DoorOpen}
          title={t('rooms.noTypesTitle')}
          description={t('rooms.noTypesDescription')}
          action={<Button asChild variant="primary"><Link to="/app/settings/room-types/new">{t('roomTypes.new')}</Link></Button>}
        />
      ) : allRooms.length === 0 ? (
        <EmptyState
          icon={DoorOpen}
          title={t('rooms.emptyTitle')}
          description={t('rooms.emptyDescription')}
          action={canManage && <Button variant="primary" onClick={() => setBulkCreate(true)}>{t('rooms.bulkCreate')}</Button>}
        />
      ) : (
        <div className="grid gap-4">
          <div role="search" className="flex flex-wrap items-center gap-2">
            <Input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('rooms.search')}
              aria-label={t('rooms.search')}
              className="h-8 w-full sm:w-64"
            />
            <FilterSelect label={t('fields.room_type')} allLabel={t('rooms.allTypes')} value={typeFilter} onChange={setTypeFilter}
                          options={types.map((type) => ({ value: type.id, label: `${type.code} · ${tr(type.name, i18n.language)}` }))} />
            <FilterSelect label={t('fields.floor')} allLabel={t('rooms.allFloors')} value={floorFilter} onChange={setFloorFilter}
                          options={floors.map((floor) => ({ value: floor, label: t('rooms.floorN', { floor }) }))} />
            <FilterSelect label={t('rooms.state')} allLabel={t('rooms.allStates')} value={statusFilter} onChange={setStatusFilter}
                          options={[
                            ...HOUSEKEEPING_STATUSES.map((status) => ({ value: status, label: t(`common:status.room.${status}`) })),
                            { value: 'blocked', label: t('rooms.blocked') },
                            { value: 'inactive', label: t('rooms.inactive') },
                          ]} />
            <span className="ml-auto text-xs text-muted num">{t('rooms.showing', { count: visible.length, total: allRooms.length })}</span>
          </div>

          {groups.length === 0 ? (
            <EmptyState title={t('rooms.noMatchTitle')} description={t('rooms.noMatchDescription')} />
          ) : (
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
              <table className="w-full border-collapse text-sm">
                <thead className="sr-only">
                  <tr>
                    {canManage && <th scope="col">{t('rooms.select')}</th>}
                    <th scope="col">{t('fields.number')}</th>
                    <th scope="col">{t('fields.floor')}</th>
                    <th scope="col">{t('rooms.bedsAndSize')}</th>
                    <th scope="col">{t('fields.housekeeping_status')}</th>
                    <th scope="col">{t('rooms.ownValues')}</th>
                    <th scope="col">{t('rooms.open')}</th>
                  </tr>
                </thead>
                {groups.map(({ type, rooms: groupRooms }) => (
                  <RoomGroup
                    key={type.id}
                    type={type}
                    rooms={groupRooms}
                    canManage={canManage}
                    selected={selected}
                    onToggle={toggle}
                    onOpen={(room) => navigate(`/app/settings/rooms/${room.id}`)}
                  />
                ))}
              </table>
            </div>
          )}
        </div>
      )}

      {canManage && selected.size > 0 && (
        <div
          role="region"
          aria-label={t('rooms.selection')}
          className="sticky bottom-4 z-20 mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface/95 px-4 py-3 shadow-lg backdrop-blur animate-pop-in"
        >
          <p className="flex-1 text-[13px] font-semibold num">{t('rooms.selectedCount', { count: selected.size })}</p>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
            <X aria-hidden />
            {t('rooms.clearSelection')}
          </Button>
          <Button variant="primary" size="sm" onClick={() => setBulkEdit(true)}>
            {t('rooms.bulkEdit')}
          </Button>
        </div>
      )}

      {canManage && roomTypes.data && (
        <>
          <BulkCreateDialog open={bulkCreate} onOpenChange={setBulkCreate} roomTypes={types}
                            defaultRoomTypeId={typeFilter !== ALL ? typeFilter : undefined} />
          <CreateRoomDialog open={createOne} onOpenChange={setCreateOne} roomTypes={types} />
          <BulkEditSheet open={bulkEdit} onOpenChange={setBulkEdit} rooms={selectedRooms} roomTypes={types}
                         definitions={definitions.data ?? []} onDone={() => setSelected(new Set())} />
        </>
      )}
    </>
  )
}

function FilterSelect({ label, allLabel, value, onChange, options }: {
  label: string
  /** What the "no filter" option says, e.g. "Todas las categorías". */
  allLabel: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <Select name={`filter-${label}`} value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className={cn('h-8 w-auto min-w-36 text-[13px]', value !== ALL && 'border-accent/60')}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function RoomGroup({ type, rooms, canManage, selected, onToggle, onOpen }: {
  type: RoomType
  rooms: Room[]
  canManage: boolean
  selected: Set<string>
  onToggle: (ids: string[], on: boolean) => void
  onOpen: (room: Room) => void
}) {
  const { t, i18n } = useTranslation('inventory')
  const headingId = `room-group-${type.id}`
  const ids = rooms.map((room) => room.id)
  const count = ids.filter((id) => selected.has(id)).length
  const capacity =
    type.kind === 'dorm'
      ? t('rooms.perBed')
      : type.base_occupancy === type.max_occupancy
        ? t('common.people', { count: type.max_occupancy })
        : t('common.peopleRange', { min: type.base_occupancy, max: type.max_occupancy })

  return (
    <tbody aria-labelledby={headingId} className="border-t border-border first-of-type:border-t-0">
      <tr className="bg-surface-2/70">
        <th scope="rowgroup" colSpan={canManage ? 7 : 6} className="px-3 py-2 text-left font-normal">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {canManage && (
              <Checkbox
                aria-label={t('rooms.selectGroup', { name: tr(type.name, i18n.language) })}
                checked={count === 0 ? false : count === ids.length ? true : 'indeterminate'}
                onCheckedChange={(value) => onToggle(ids, value === true)}
              />
            )}
            <span id={headingId}>
              <CategoryChip code={type.code} name={type.name} color={type.color} />
            </span>
            <span className="text-xs text-muted">
              {t('common.rooms', { count: rooms.length })} · {type.kind === 'dorm' ? t('common.beds', { count: type.units_count }) : capacity}
            </span>
            {!type.is_active && <Badge tone="stone">{t('common.inactive')}</Badge>}
            <Link to={`/app/settings/room-types/${type.id}`} className="ml-auto text-xs font-semibold text-accent-ink hover:underline">
              {t('rooms.editType')}
            </Link>
          </div>
        </th>
      </tr>
      {rooms.map((room) => {
        const own = room.overridden_fields.length + room.extra_amenities.length + room.removed_amenities.length
        return (
          <tr
            key={room.id}
            onClick={() => onOpen(room)}
            className={cn(
              'cursor-pointer border-t border-border/70 transition-colors hover:bg-surface-2/60',
              selected.has(room.id) && 'bg-accent-soft/40',
            )}
          >
            {canManage && (
              <td className="w-10 px-3 py-2" onClick={(event) => event.stopPropagation()}>
                <Checkbox
                  aria-label={t('rooms.selectRoom', { number: room.number })}
                  checked={selected.has(room.id)}
                  onCheckedChange={(value) => onToggle([room.id], value === true)}
                />
              </td>
            )}
            <td className="px-3 py-2">
              <Link
                to={`/app/settings/rooms/${room.id}`}
                onClick={(event) => event.stopPropagation()}
                className="flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <RoomKeyTag number={room.number} status={room.housekeeping_status} inactive={!room.is_active} />
                {room.name && <span className="truncate text-muted">{room.name}</span>}
              </Link>
            </td>
            <td className="hidden px-3 py-2 text-muted sm:table-cell num">{room.floor ? t('rooms.floorN', { floor: room.floor }) : '—'}</td>
            <td className="hidden px-3 py-2 text-muted md:table-cell">
              {room.kind === 'dorm'
                ? t('common.beds', { count: room.active_beds_count })
                : `${bedsSummary(room.effective.beds, t)} · ${sizeLabel(room.effective.size_m2, i18n.language)}`}
            </td>
            <td className="px-3 py-2">
              <span className="flex flex-wrap items-center gap-1.5">
                <RoomStatusBadge status={room.housekeeping_status} />
                {room.active_block && (
                  <Badge tone="stone" className="hatch">
                    <Ban aria-hidden />
                    {t(`blockKinds.${room.active_block.kind}`)}
                  </Badge>
                )}
                {!room.is_active && <Badge tone="stone">{t('common.inactive')}</Badge>}
              </span>
            </td>
            <td className="hidden px-3 py-2 lg:table-cell">
              {own > 0 && <Badge tone="accent">{t('rooms.own', { count: own })}</Badge>}
            </td>
            <td className="w-8 px-2 py-2 text-subtle">
              <ChevronRight aria-hidden className="size-4" />
            </td>
          </tr>
        )
      })}
    </tbody>
  )
}
