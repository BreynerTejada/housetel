import { enUS, es } from 'date-fns/locale'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ComponentProps } from 'react'
import { DayPicker } from 'react-day-picker'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/** react-day-picker v9 styled with the design tokens; locale follows the UI language. */
export function Calendar({ className, classNames, showOutsideDays = true, ...props }: ComponentProps<typeof DayPicker>) {
  const { i18n } = useTranslation()
  return (
    <DayPicker
      locale={i18n.language === 'en' ? enUS : es}
      showOutsideDays={showOutsideDays}
      className={cn('p-1 text-sm', className)}
      classNames={{
        months: 'relative flex flex-col gap-6 sm:flex-row',
        month: 'flex flex-col gap-3',
        month_caption: 'flex h-8 items-center justify-center font-bold capitalize',
        caption_label: 'text-sm',
        nav: 'absolute inset-x-0 top-0 flex h-8 items-center justify-between',
        button_previous:
          'inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg disabled:opacity-40',
        button_next:
          'inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg disabled:opacity-40',
        month_grid: 'border-collapse',
        weekdays: 'flex',
        weekday: 'w-9 text-[11px] font-semibold uppercase text-subtle',
        week: 'mt-1 flex w-full',
        day: 'group relative size-9 p-0 text-center',
        day_button: cn(
          'num inline-flex size-9 items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-surface-2',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
          'group-data-[selected=true]:bg-accent group-data-[selected=true]:text-on-accent group-data-[selected=true]:hover:bg-accent-hover',
        ),
        today: '[&>button]:font-extrabold [&>button]:text-accent-ink [&>button]:underline [&>button]:decoration-2 [&>button]:underline-offset-4',
        outside: 'text-subtle opacity-60',
        disabled: 'text-subtle opacity-40 [&>button]:pointer-events-none',
        range_start: 'rounded-l-md bg-accent-soft',
        range_middle: 'bg-accent-soft [&>button]:!bg-transparent [&>button]:!text-accent-ink [&>button]:rounded-none',
        range_end: 'rounded-r-md bg-accent-soft',
        hidden: 'invisible',
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) =>
          orientation === 'left' ? <ChevronLeft aria-hidden className="size-4" /> : <ChevronRight aria-hidden className="size-4" />,
      }}
      {...props}
    />
  )
}
