import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { CompareMode, ReportDef } from '../api'
import { PICKUP_WINDOWS } from '../lib/catalog'
import type { ReportFilters } from '../lib/filters'
import { RangeControl } from './RangeControl'

const NONE = 'none'

/** One row of filters above everything they scope (dataviz): range first, then comparison and grouping. */
export function FilterBar({ report, filters, businessDate }: { report: ReportDef; filters: ReportFilters; businessDate: string }) {
  const { t } = useTranslation('reports')
  const hasControls = filters.range || report.compare || report.group_by.length > 0 || report.window_param
  if (!hasControls) return null

  return (
    <div role="group" aria-label={t('filters.label')} className="flex flex-wrap items-end gap-x-4 gap-y-3">
      {filters.range && (
        <Field label={t('filters.range')}>
          <RangeControl
            presets={filters.presets}
            preset={filters.preset}
            range={filters.range}
            businessDate={businessDate}
            onPreset={filters.setPreset}
            onCustom={filters.setCustomRange}
          />
        </Field>
      )}

      {report.compare && (
        <Field label={t('filters.compare')}>
          <Select
            value={filters.compare ?? NONE}
            onValueChange={(value) => filters.setCompare(value === NONE ? null : (value as CompareMode))}
          >
            <SelectTrigger className="h-9 w-full sm:w-48" aria-label={t('filters.compare')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[NONE, 'previous_period', 'previous_year'].map((mode) => (
                <SelectItem key={mode} value={mode}>
                  {t(`filters.compareModes.${mode}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}

      {report.group_by.length > 0 && filters.groupBy && (
        <Field label={t('filters.groupBy')}>
          <ToggleGroup
            type="single"
            value={filters.groupBy}
            onValueChange={(value) => value && filters.setGroupBy(value)}
            aria-label={t('filters.groupBy')}
            className="max-w-full overflow-x-auto [scrollbar-width:none]"
          >
            {report.group_by.map((group) => (
              <ToggleGroupItem key={group} value={group} className="shrink-0">
                {t(`filters.groups.${group}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
      )}

      {report.window_param && filters.days !== null && (
        <Field label={t('filters.window')}>
          <ToggleGroup
            type="single"
            value={String(filters.days)}
            onValueChange={(value) => value && filters.setDays(Number(value))}
            aria-label={t('filters.window')}
          >
            {PICKUP_WINDOWS.map((days) => (
              <ToggleGroupItem key={days} value={String(days)}>
                {t('filters.windowDays', { count: days })}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex w-full min-w-0 flex-col gap-1.5 sm:w-auto">
      <span className="eyebrow">{label}</span>
      {children}
    </div>
  )
}
