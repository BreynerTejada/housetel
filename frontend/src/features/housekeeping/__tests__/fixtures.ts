/** Test data with the exact shapes of the housekeeping API (backend `apps/housekeeping/api/serializers.py`). */
import { http, HttpResponse } from 'msw'
import { auroraMembership, makeMe } from '@/test/fixtures'
import { server } from '@/test/server'
import type {
  BoardRoom,
  HkSettings,
  HkSummary,
  HkTask,
  Housekeeper,
  HousekeepingBoard,
  MaintenanceTicket,
  RoomRef,
  StaffResponse,
  TicketPhoto,
} from '../api'

export const LUZ = { id: 'user-luz', full_name: 'Luz Marina Pérez', email: 'limpieza@casaaurora.co' }
export const ROSA = { id: 'user-rosa', full_name: 'Rosa Díaz', email: 'rosa@casaaurora.co' }
export const JORGE = { id: 'user-jorge', full_name: 'Jorge Técnico', email: 'jorge@casaaurora.co' }

/** Luz Marina: the `housekeeping` system role (view + work). */
export function housekeeperMe() {
  return makeMe({
    id: LUZ.id,
    email: LUZ.email,
    full_name: LUZ.full_name,
    memberships: [auroraMembership(['housekeeping.view', 'housekeeping.work', 'inventory.view'], 'housekeeping')],
  })
}

export function supervisorMe() {
  return makeMe({
    id: 'user-sup',
    email: 'supervisora@casaaurora.co',
    full_name: 'Marta Supervisora',
    memberships: [auroraMembership(['housekeeping.*', 'inventory.view', 'control.alerts'], 'housekeeping_supervisor')],
  })
}

export function maintenanceMe() {
  return makeMe({
    id: JORGE.id,
    email: JORGE.email,
    full_name: JORGE.full_name,
    memberships: [auroraMembership(['housekeeping.view', 'housekeeping.maintenance', 'inventory.view'], 'maintenance')],
  })
}

const ROOM_TYPES = {
  DBL: { id: 'rt-dbl', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, color: '#4E6C88', kind: 'private' },
  SUP: { id: 'rt-sup', code: 'SUP', name: { es: 'Superior', en: 'Superior' }, color: '#5F7F66', kind: 'private' },
  STE: { id: 'rt-ste', code: 'STE', name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' }, color: '#B4583B', kind: 'private' },
} as const

export function makeRoomRef(number: string, overrides: Partial<RoomRef> = {}): RoomRef {
  const type = number.startsWith('3') ? ROOM_TYPES.STE : number.startsWith('2') ? ROOM_TYPES.SUP : ROOM_TYPES.DBL
  return {
    id: `room-${number}`,
    number,
    name: '',
    floor: number.slice(0, 1),
    housekeeping_status: 'dirty',
    room_type: { ...type, name: { ...type.name } },
    ...overrides,
  }
}

export function makeTask(overrides: Partial<HkTask> & { number?: string } = {}): HkTask {
  const { number = '101', ...rest } = overrides
  return {
    id: `task-${number}`,
    room: makeRoomRef(number),
    bed: null,
    kind: 'departure_clean',
    status: 'pending',
    priority: 'normal',
    business_date: '2026-09-25',
    assigned_to: LUZ,
    estimated_minutes: 30,
    started_at: null,
    finished_at: null,
    finished_by: null,
    notes: '',
    reservation: null,
    created_source: 'daily',
    waiting_for_checkout: false,
    arrival_today: null,
    overdue: false,
    created_at: '2026-09-25T07:00:00-05:00',
    updated_at: '2026-09-25T07:00:00-05:00',
    ...rest,
  }
}

export function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results }
}

export const SETTINGS: HkSettings = {
  stayover_frequency_days: 1,
  require_inspection: false,
  auto_assign: true,
  minutes_per_shift: 420,
}

export function makeSummary(overrides: Partial<HkSummary> = {}): HkSummary {
  return {
    business_date: '2026-09-25',
    rooms: { total: 6, clean: 2, dirty: 2, inspected: 1, out_of_service: 1, occupied: 3 },
    tasks: { total: 5, pending: 2, in_progress: 1, done: 2, inspections_pending: 1, unassigned: 1 },
    minutes: { total: 150, done: 60 },
    tickets: { open: 2, blocking: 1 },
    ...overrides,
  }
}

export function makeHousekeeper(user: typeof LUZ, overrides: Partial<Housekeeper> = {}): Housekeeper {
  return { ...user, minutes: 0, minutes_done: 0, tasks: 0, tasks_done: 0, ...overrides }
}

export function makeBoardRoom(number: string, overrides: Partial<BoardRoom> = {}): BoardRoom {
  const ref = makeRoomRef(number, { housekeeping_status: overrides.housekeeping_status ?? 'clean' })
  return {
    ...ref,
    occupied: false,
    in_house: null,
    arrival_today: null,
    tasks: [],
    active_block: null,
    open_tickets: 0,
    ...overrides,
  }
}

/** Floor 1: 101 dirty (departure for Luz, guest left, VIP arriving 15:00), 102 clean (stayover, unassigned).
 * Floor 2: 201 out of service (blocked by a ticket), 202 inspected. */
export function makeBoard(overrides: Partial<HousekeepingBoard> = {}): HousekeepingBoard {
  const departure = makeTask({
    number: '101',
    priority: 'high',
    arrival_today: { code: 'HT-ARR101', eta: '15:00', is_vip: true },
  })
  const stayover = makeTask({ number: '102', kind: 'stayover', assigned_to: null, estimated_minutes: 15 })
  return {
    business_date: '2026-09-25',
    settings: SETTINGS,
    summary: makeSummary(),
    staff: [makeHousekeeper(LUZ, { minutes: 30, tasks: 1 }), makeHousekeeper(ROSA)],
    floors: [
      {
        floor: '1',
        rooms: [
          makeBoardRoom('101', {
            housekeeping_status: 'dirty',
            arrival_today: { code: 'HT-ARR101', eta: '15:00', is_vip: true },
            tasks: [departure],
          }),
          makeBoardRoom('102', {
            housekeeping_status: 'clean',
            occupied: true,
            in_house: { code: 'HT-IN102', checkout_date: '2026-09-27', departs_today: false, guests: 2, is_vip: false },
            tasks: [stayover],
          }),
        ],
      },
      {
        floor: '2',
        rooms: [
          makeBoardRoom('201', {
            housekeeping_status: 'out_of_service',
            active_block: {
              id: 'block-1',
              kind: 'out_of_order',
              reason: 'Mantenimiento: Aire acondicionado no enfría',
              start_date: '2026-09-25',
              end_date: '2026-09-27',
            },
            open_tickets: 1,
          }),
          makeBoardRoom('202', { housekeeping_status: 'inspected' }),
        ],
      },
    ],
    ...overrides,
  }
}

export const STAFF: StaffResponse = {
  housekeepers: [makeHousekeeper(LUZ, { minutes: 30, tasks: 1 }), makeHousekeeper(ROSA)],
  maintenance: [{ ...JORGE, open_tickets: 1 }],
}

export function makePhoto(overrides: Partial<TicketPhoto> = {}): TicketPhoto {
  return {
    id: 'photo-1',
    content_type: 'image/jpeg',
    size: 48213,
    file_url: '/api/v1/housekeeping/ticket-photos/photo-1/file/',
    uploaded_by: LUZ,
    created_at: '2026-09-25T09:12:00-05:00',
    ...overrides,
  }
}

export function makeTicket(overrides: Partial<MaintenanceTicket> = {}): MaintenanceTicket {
  return {
    id: 'ticket-1',
    room: makeRoomRef('102', { housekeeping_status: 'clean' }),
    location: '',
    title: 'Grifo del lavamanos gotea',
    description: 'Gotea aunque esté cerrado.',
    priority: 'normal',
    status: 'open',
    blocks_room: false,
    blocked_until: null,
    block: null,
    reported_by: LUZ,
    assigned_to: null,
    started_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_notes: '',
    photos: [],
    created_at: '2026-09-25T09:12:00-05:00',
    updated_at: '2026-09-25T09:12:00-05:00',
    ...overrides,
  }
}

/** Answers `GET board/` (and `staff/`) with `board`. */
export function serveBoard(board: HousekeepingBoard = makeBoard()) {
  server.use(
    http.get('/api/v1/housekeeping/board/', () => HttpResponse.json(board)),
    http.get('/api/v1/housekeeping/staff/', () => HttpResponse.json(STAFF)),
  )
}
