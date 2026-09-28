import {
  BadgePercent,
  BedDouble,
  CalendarClock,
  CalendarRange,
  ChartLine,
  ChartNoAxesColumn,
  CircleSlash,
  Coins,
  DoorClosed,
  DoorOpen,
  Globe,
  HandCoins,
  Hourglass,
  Landmark,
  Layers,
  LogIn,
  LogOut,
  ReceiptText,
  Sparkles,
  TrendingUp,
  UserX,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import type { RangeKind, ReportCategory, ReportDef } from '../api'

/** Hub order (plan C10): Performance, Operations, Finance, Taxes. */
export const CATEGORY_ORDER: ReportCategory[] = ['performance', 'operations', 'finance', 'taxes']

export const CATEGORY_ICON: Record<ReportCategory, LucideIcon> = {
  performance: ChartLine,
  operations: BedDouble,
  finance: Wallet,
  taxes: Landmark,
}

/** Order inside each category (the most used first; MVP priorities lead). */
export const REPORT_ORDER = [
  'performance',
  'revenue-by-segment',
  'forecast',
  'pickup',
  'cancellations',
  'booking-window',
  'guests-by-nationality',
  'arrivals',
  'departures',
  'in-house',
  'no-shows',
  'occupancy-outlook',
  'housekeeping-status',
  'daily-revenue',
  'payments-by-method',
  'receivables',
  'cash-shifts',
  'taxes',
]

export const REPORT_ICON: Record<string, LucideIcon> = {
  performance: TrendingUp,
  'revenue-by-segment': Layers,
  pickup: CalendarClock,
  forecast: CalendarRange,
  cancellations: CircleSlash,
  'booking-window': Hourglass,
  'guests-by-nationality': Globe,
  arrivals: LogIn,
  departures: LogOut,
  'in-house': DoorClosed,
  'no-shows': UserX,
  'housekeeping-status': Sparkles,
  'occupancy-outlook': ChartNoAxesColumn,
  'daily-revenue': Coins,
  'payments-by-method': HandCoins,
  'cash-shifts': Wallet,
  receivables: ReceiptText,
  taxes: BadgePercent,
}

export function reportIcon(id: string): LucideIcon {
  return REPORT_ICON[id] ?? DoorOpen
}

export function sortReports(reports: ReportDef[]): ReportDef[] {
  const rank = (id: string) => {
    const index = REPORT_ORDER.indexOf(id)
    return index === -1 ? REPORT_ORDER.length : index
  }
  return [...reports].sort((a, b) => rank(a.id) - rank(b.id))
}

// ---- Date presets -------------------------------------------------------------------------------------

export type PresetId =
  | 'today'
  | 'yesterday'
  | 'tomorrow'
  | 'thisWeek'
  | 'thisMonth'
  | 'lastMonth'
  | 'last30'
  | 'next14'
  | 'next30'
  | 'next90'

/** Presets offered per kind of range (plan C10: Hoy, Ayer, Esta semana, Este mes, Mes pasado, Últimos 30 días). */
export const PRESETS_BY_KIND: Record<Exclude<RangeKind, 'none'>, PresetId[]> = {
  past: ['today', 'yesterday', 'thisWeek', 'thisMonth', 'lastMonth', 'last30'],
  any: ['today', 'yesterday', 'thisWeek', 'thisMonth', 'lastMonth', 'last30', 'next30'],
  future: ['next14', 'next30', 'next90', 'thisWeek', 'thisMonth'],
  date: ['today', 'yesterday', 'tomorrow', 'thisWeek'],
}

/** Backend preset ids (catalog `default_preset`) → frontend ids. */
const BACKEND_PRESETS: Record<string, PresetId> = {
  today: 'today',
  yesterday: 'yesterday',
  this_week: 'thisWeek',
  this_month: 'thisMonth',
  last_month: 'lastMonth',
  last30: 'last30',
  next14: 'next14',
  next30: 'next30',
  next90: 'next90',
}

export function defaultPreset(report: ReportDef): PresetId {
  const fromBackend = report.default_preset ? BACKEND_PRESETS[report.default_preset] : undefined
  if (fromBackend) return fromBackend
  return report.range_kind === 'future' ? 'next30' : report.range_kind === 'date' ? 'today' : 'thisMonth'
}

export const PICKUP_WINDOWS = [1, 7, 14, 30] as const

/** Reports whose nights from the business date on are a forecast (on the books), shown as such in the ruler. */
export const FORECAST_REPORTS = new Set(['performance', 'revenue-by-segment', 'guests-by-nationality', 'forecast', 'occupancy-outlook'])
