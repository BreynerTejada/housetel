import { Coins, LogIn, TrendingUp } from 'lucide-react'
import type { CommandItem } from '@/app/extensions'

// ⌘K palette (plan C10): jump straight to the reports people open every day.
export const commands: CommandItem[] = [
  {
    id: 'reports.performance',
    group: 'reports:commands.group',
    labelKey: 'reports:commands.performance',
    icon: TrendingUp,
    keywords: ['ocupación', 'occupancy', 'adr', 'revpar', 'rendimiento', 'performance', 'reporte', 'report'],
    permission: 'reports.performance',
    perform: ({ navigate }) => navigate('/app/reports/performance'),
  },
  {
    id: 'reports.arrivals',
    group: 'reports:commands.group',
    labelKey: 'reports:commands.arrivals',
    icon: LogIn,
    keywords: ['llegadas', 'arrivals', 'hoy', 'today', 'reporte', 'report'],
    permission: 'reports.operational',
    perform: ({ navigate }) => navigate('/app/reports/arrivals?preset=today'),
  },
  {
    id: 'reports.dailyRevenue',
    group: 'reports:commands.group',
    labelKey: 'reports:commands.dailyRevenue',
    icon: Coins,
    keywords: ['ingresos', 'revenue', 'ventas', 'sales', 'diario', 'daily', 'reporte', 'report'],
    permission: 'reports.financial',
    perform: ({ navigate }) => navigate('/app/reports/daily-revenue'),
  },
]
