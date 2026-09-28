import { useTranslation } from 'react-i18next'
import { KpiTile } from '@/components/KpiTile'
import { formatNumber, formatPercent, normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CompareMode, Kpi } from '../api'
import { compactMoney, countryName } from '../lib/format'
import { KPI_TILE_CLASS } from '../lib/styles'

/** Columns per number of tiles, so a row never ends with one orphan tile on desktop. */
const GRID: Record<number, string> = {
  1: 'sm:grid-cols-2',
  2: 'sm:grid-cols-2',
  3: 'sm:grid-cols-3',
  4: 'sm:grid-cols-2 lg:grid-cols-4',
  5: 'sm:grid-cols-3 lg:grid-cols-5',
  6: 'sm:grid-cols-3 xl:grid-cols-6',
  7: 'sm:grid-cols-4',
}

function kpiValue(kpi: Kpi, currency: string, lang: Lang, t: (key: string, options?: Record<string, unknown>) => string): string {
  const { value } = kpi
  if (value === null || value === undefined || value === '') return '—'
  if (kpi.type === 'text') return kpi.key === 'top_country' && typeof value === 'string' && value.length === 2 ? countryName(value, lang, '—') : String(value)
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (kpi.type === 'money') return compactMoney(n, currency, lang, 10_000_000)
  if (kpi.type === 'percent') return formatPercent(n, 1, lang)
  const text = formatNumber(n, lang, 1)
  return kpi.unit ? t(`kpi.${kpi.unit}`, { value: text }) : text
}

function kpiDelta(kpi: Kpi, lang: Lang, t: (key: string, options?: Record<string, unknown>) => string) {
  if (kpi.change === undefined || kpi.change === null) return { delta: null, label: undefined }
  const change = Number(kpi.change)
  if (!Number.isFinite(change)) return { delta: null, label: undefined }
  if (kpi.type === 'percent') {
    // Occupancy and shares move in percentage points, never in % of a %.
    return { delta: change, label: t('kpi.pp', { value: formatNumber(Math.abs(change), lang, 1) }) }
  }
  if (kpi.change_pct === null || kpi.change_pct === undefined) return { delta: change === 0 ? 0 : null, label: undefined }
  return { delta: kpi.change_pct, label: formatPercent(Math.abs(kpi.change_pct), 1, lang) }
}

/** KPI tiles of a report (dataviz stat-tile contract): value, signed change vs the named comparison period. */
export function KpiRow({ kpis, currency, compare }: { kpis: Kpi[]; currency: string; compare: CompareMode | null }) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  if (kpis.length === 0) return null
  const period = compare ? t(`kpi.vs_${compare}`) : undefined

  return (
    <div className={cn('grid grid-cols-2 gap-3', GRID[Math.min(kpis.length, 7)])}>
      {kpis.map((kpi) => {
        const { delta, label } = kpiDelta(kpi, lang, t)
        return (
          <KpiTile
            key={kpi.key}
            label={kpi.label}
            value={kpiValue(kpi, currency, lang, t)}
            delta={compare ? delta : undefined}
            deltaLabel={label}
            deltaPeriod={period}
            intent={kpi.intent}
            className={KPI_TILE_CLASS}
          />
        )
      })}
    </div>
  )
}
