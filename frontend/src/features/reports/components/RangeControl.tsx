import { CalendarRange, Check, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { useTranslation } from 'react-i18next'
import { Calendar } from '@/components/ui/calendar'
import { fieldBase } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMediaQuery } from '@/lib/hooks'
import { formatDateRange, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { PresetId } from '../lib/catalog'
import { presetRange, type ReportRange } from '../lib/presets'

interface RangeControlProps {
  presets: PresetId[]
  preset: PresetId | 'custom' | null
  range: ReportRange
  businessDate: string
  onPreset: (id: PresetId) => void
  onCustom: (range: ReportRange) => void
}

/**
 * Date range of a report: presets as rows (the selected one checked) and the custom range behind a hairline.
 * Both days of a range count, so picking the same day twice is a valid one-day range.
 */
export function RangeControl({ presets, preset, range, businessDate, onPreset, onCustom }: RangeControlProps) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const wide = useMediaQuery('(min-width: 768px)')
  const [open, setOpen] = useState(false)
  const [custom, setCustom] = useState(false)
  const [draft, setDraft] = useState<DateRange | undefined>()

  const label = preset ? t(`filters.presets.${preset}`) : t('filters.range')

  function openChange(next: boolean) {
    setOpen(next)
    if (next) {
      setCustom(preset === 'custom')
      setDraft({ from: parseDate(range.start) ?? undefined, to: parseDate(range.end) ?? undefined })
    }
  }

  function pick(id: PresetId) {
    onPreset(id)
    setOpen(false)
  }

  function handleDay(_: DateRange | undefined, clicked: Date) {
    const start = draft?.from
    if (!start || draft?.to) {
      setDraft({ from: clicked, to: undefined })
      return
    }
    const [from, to] = clicked < start ? [clicked, start] : [start, clicked]
    setDraft({ from, to })
    onCustom({ start: toISODate(from), end: toISODate(to) })
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={openChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${t('filters.range')}: ${label}, ${formatDateRange(range.start, range.end, lang)}`}
          className={cn(fieldBase, 'flex h-9 w-full items-center gap-2 px-3 text-left text-sm sm:w-auto')}
        >
          <CalendarRange aria-hidden className="size-4 shrink-0 text-muted" />
          <span className="font-semibold whitespace-nowrap text-fg">{label}</span>
          <span className="num truncate text-muted">{formatDateRange(range.start, range.end, lang)}</span>
          <ChevronDown aria-hidden className="ml-auto size-4 shrink-0 text-subtle sm:ml-1" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto max-w-[calc(100vw-2rem)] p-0" align="start">
        <div className="flex flex-col md:flex-row">
          <div className="flex min-w-60 flex-col">
            <ul role="listbox" aria-label={t('filters.range')} className="flex flex-col p-1.5">
              {presets.map((id) => {
                const selected = preset === id
                const value = presetRange(id, businessDate)
                return (
                  <li key={id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() => pick(id)}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] transition-colors',
                        'hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none',
                        selected ? 'font-bold text-fg' : 'font-medium text-fg',
                      )}
                    >
                      <Check aria-hidden strokeWidth={2.75} className={cn('size-4 shrink-0 text-accent-ink', !selected && 'invisible')} />
                      <span className="flex-1">{t(`filters.presets.${id}`)}</span>
                      <span className="num text-xs font-medium whitespace-nowrap text-muted">
                        {formatDateRange(value.start, value.end, lang)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <div className="border-t border-border p-1.5">
              <button
                type="button"
                aria-expanded={custom}
                onClick={() => setCustom((value) => !value)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] transition-colors',
                  'hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none',
                  preset === 'custom' ? 'font-bold' : 'font-medium',
                )}
              >
                <Check aria-hidden strokeWidth={2.75} className={cn('size-4 shrink-0 text-accent-ink', preset !== 'custom' && 'invisible')} />
                <span className="flex-1">{t('filters.customRange')}</span>
                <ChevronDown aria-hidden className={cn('size-4 text-subtle transition-transform', custom && 'rotate-180 md:-rotate-90')} />
              </button>
            </div>
          </div>
          {custom && (
            <div className="border-t border-border p-2 md:border-t-0 md:border-l">
              <p className="px-1 pb-1 text-xs text-muted">{t('filters.customHint')}</p>
              <Calendar
                mode="range"
                numberOfMonths={wide ? 2 : 1}
                selected={draft}
                onSelect={handleDay}
                defaultMonth={draft?.from ?? parseDate(businessDate) ?? undefined}
                today={parseDate(businessDate) ?? undefined}
              />
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
