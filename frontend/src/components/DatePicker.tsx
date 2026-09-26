import { differenceInCalendarDays, isSameDay } from 'date-fns'
import { CalendarDays, CalendarRange } from 'lucide-react'
import { useState } from 'react'
import type { DateRange, Matcher } from 'react-day-picker'
import { useTranslation } from 'react-i18next'
import { rangePreset, type DateRangeValue, type RangePresetId } from '@/lib/date-ranges'
import { formatDate, formatDateRange, nightsBetween, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Button } from './ui/button'
import { Calendar } from './ui/calendar'
import { fieldBase } from './ui/input'
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover'

function disabledDays(min?: string, max?: string): Matcher[] {
  const matchers: Matcher[] = []
  const before = parseDate(min)
  const after = parseDate(max)
  if (before) matchers.push({ before })
  if (after) matchers.push({ after })
  return matchers
}

const triggerClass = cn(fieldBase, 'flex h-9 items-center gap-2 px-3 text-left text-sm')

interface DatePickerProps {
  /** `YYYY-MM-DD` or null. */
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  /** Earliest / latest selectable day (`YYYY-MM-DD`). */
  min?: string
  max?: string
  disabled?: boolean
  id?: string
  className?: string
  'aria-label'?: string
  'aria-invalid'?: boolean
}

export function DatePicker({ value, onChange, placeholder, min, max, disabled, id, className, ...aria }: DatePickerProps) {
  const { t, i18n } = useTranslation()
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const selected = parseDate(value) ?? undefined
  const text = value ? formatDate(value, 'EEE d MMM yyyy', lang) : (placeholder ?? t('date.placeholder'))

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          disabled={disabled}
          aria-label={aria['aria-label'] ? `${aria['aria-label']}: ${text}` : undefined}
          aria-invalid={aria['aria-invalid']}
          className={cn(triggerClass, className)}
        >
          <CalendarDays aria-hidden className="size-4 shrink-0 text-muted" />
          <span className={cn('num truncate', !value && 'text-subtle')}>{text}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          disabled={disabledDays(min, max)}
          onSelect={(day) => {
            onChange(day ? toISODate(day) : null)
            setOpen(false)
          }}
        />
      </PopoverContent>
    </Popover>
  )
}

interface DateRangePickerProps {
  value: DateRangeValue | null
  onChange: (value: DateRangeValue | null) => void
  /** Reference day for presets and the first month shown (use the property's business date). */
  today?: string
  presets?: RangePresetId[]
  /** Adds "3 noches" to the trigger (stays: `to` is the checkout day). */
  showNights?: boolean
  /** Minimum nights between the two days (stays: 1). */
  minNights?: number
  min?: string
  max?: string
  numberOfMonths?: number
  placeholder?: string
  disabled?: boolean
  id?: string
  className?: string
  'aria-label'?: string
  'aria-invalid'?: boolean
}

/**
 * Two clicks pick a range (in any order). For stays `to` is the checkout day (exclusive); for reports
 * both ends are inclusive — the picker only returns the two days.
 */
export function DateRangePicker({
  value,
  onChange,
  today,
  presets = [],
  showNights = false,
  minNights = 0,
  min,
  max,
  numberOfMonths = 2,
  placeholder,
  disabled,
  id,
  className,
  ...aria
}: DateRangePickerProps) {
  const { t, i18n } = useTranslation()
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<DateRange | undefined>()
  const reference = today ?? toISODate(new Date())

  const nights = value ? nightsBetween(value.from, value.to) : 0
  const text = value ? formatDateRange(value.from, value.to, lang) : (placeholder ?? t('date.rangePlaceholder'))

  function openChange(next: boolean) {
    if (next) setDraft(value ? { from: parseDate(value.from) ?? undefined, to: parseDate(value.to) ?? undefined } : undefined)
    setOpen(next)
  }

  function commit(range: DateRangeValue | null) {
    onChange(range)
    setOpen(false)
  }

  function handleSelect(_: DateRange | undefined, clicked: Date) {
    const start = draft?.from
    if (!start || draft?.to) {
      setDraft({ from: clicked, to: undefined })
      return
    }
    if (isSameDay(clicked, start) && minNights > 0) return
    const [from, to] = clicked < start ? [clicked, start] : [start, clicked]
    if (differenceInCalendarDays(to, from) < minNights) return
    setDraft({ from, to })
    commit({ from: toISODate(from), to: toISODate(to) })
  }

  return (
    <Popover open={open} onOpenChange={openChange}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          disabled={disabled}
          aria-label={aria['aria-label'] ? `${aria['aria-label']}: ${text}` : undefined}
          aria-invalid={aria['aria-invalid']}
          className={cn(triggerClass, className)}
        >
          <CalendarRange aria-hidden className="size-4 shrink-0 text-muted" />
          <span className={cn('num truncate', !value && 'text-subtle')}>{text}</span>
          {showNights && value && nights > 0 && (
            <span className="ml-auto shrink-0 text-xs font-semibold text-muted">{t('date.nights', { count: nights })}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          {presets.length > 0 && (
            <div className="flex flex-wrap gap-1 border-border pb-2 sm:w-40 sm:flex-col sm:border-r sm:pr-2 sm:pb-0">
              {presets.map((preset) => (
                <Button key={preset} variant="ghost" size="sm" className="justify-start" onClick={() => commit(rangePreset(preset, reference))}>
                  {t(`date.presets.${preset}`)}
                </Button>
              ))}
            </div>
          )}
          <div>
            <Calendar
              mode="range"
              numberOfMonths={numberOfMonths}
              selected={draft}
              onSelect={handleSelect}
              defaultMonth={draft?.from ?? parseDate(reference) ?? undefined}
              disabled={disabledDays(min, max)}
            />
            {value && (
              <div className="flex justify-end border-t border-border pt-2">
                <Button variant="ghost" size="sm" onClick={() => commit(null)}>
                  {t('date.clear')}
                </Button>
              </div>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
