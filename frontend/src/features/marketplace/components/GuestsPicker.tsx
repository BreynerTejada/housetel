import { Minus, Plus, UsersRound } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { MAX_CHILD_AGE, MAX_CHILDREN, type Stay } from '../lib/search-params'
import { guestsLabel } from '../lib/text'

export type Party = Pick<Stay, 'adults' | 'children' | 'ages'>

interface CounterProps {
  label: string
  hint: string
  value: number
  min: number
  max: number
  noun: string
  onChange: (value: number) => void
}

function Counter({ label, hint, value, min, max, noun, onChange }: CounterProps) {
  const { t } = useTranslation('marketplace')
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div id={id}>
        <p className="text-sm font-semibold text-fg">{label}</p>
        <p className="text-xs text-muted">{hint}</p>
      </div>
      <div role="group" aria-labelledby={id} className="flex items-center gap-3">
        <Button
          variant="secondary"
          size="icon-sm"
          className="rounded-full"
          aria-label={t('guests.decrease', { what: noun })}
          disabled={value <= min}
          onClick={() => onChange(value - 1)}
        >
          <Minus aria-hidden />
        </Button>
        <span aria-live="polite" className="num w-5 text-center text-base font-bold text-fg">
          {value}
        </span>
        <Button
          variant="secondary"
          size="icon-sm"
          className="rounded-full"
          aria-label={t('guests.increase', { what: noun })}
          disabled={value >= max}
          onClick={() => onChange(value + 1)}
        >
          <Plus aria-hidden />
        </Button>
      </div>
    </div>
  )
}

interface GuestsPickerProps {
  value: Party
  onChange: (value: Party) => void
  id?: string
  /** Classes of the trigger button (the search bar styles it as a borderless segment). */
  className?: string
  maxAdults?: number
  'aria-labelledby'?: string
}

/**
 * Adults, children and each child's age (the age decides the child rate, so it is asked, but a party without
 * ages is still valid: the hotel then prices every child as a child).
 */
export function GuestsPicker({ value, onChange, id, className, maxAdults = 12, ...aria }: GuestsPickerProps) {
  const { t } = useTranslation('marketplace')
  const [open, setOpen] = useState(false)
  // Ages being chosen: the party only carries them once every child has one.
  const [draftAges, setDraftAges] = useState<(number | null)[]>(() => fitAges(value.ages, value.children))

  function openChange(next: boolean) {
    if (next) setDraftAges((current) => (value.ages.length === value.children ? [...value.ages] : fitAges(current, value.children)))
    setOpen(next)
  }

  function emit(adults: number, ages: (number | null)[]) {
    setDraftAges(ages)
    const complete = ages.every((age): age is number => age !== null)
    onChange({ adults, children: ages.length, ages: complete ? ages : [] })
  }

  return (
    <Popover open={open} onOpenChange={openChange}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          aria-labelledby={aria['aria-labelledby'] ? `${aria['aria-labelledby']} ${id}` : undefined}
          className={cn(
            'flex w-full items-center gap-2 text-left text-sm text-fg outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
            className,
          )}
        >
          <UsersRound aria-hidden className="size-4 shrink-0 text-muted" />
          <span className="truncate">{guestsLabel(value.adults, value.children, t)}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))] p-4">
        <div className="divide-y divide-border">
          <Counter
            label={t('guests.adultsLabel')}
            hint={t('guests.adultsHint')}
            value={value.adults}
            min={1}
            max={maxAdults}
            noun={t('guests.adultNoun')}
            onChange={(adults) => emit(adults, draftAges)}
          />
          <Counter
            label={t('guests.childrenLabel')}
            hint={t('guests.childrenHint')}
            value={draftAges.length}
            min={0}
            max={MAX_CHILDREN}
            noun={t('guests.childNoun')}
            onChange={(children) => emit(value.adults, fitAges(draftAges, children))}
          />
        </div>
        {draftAges.length > 0 && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="text-xs text-muted">{t('guests.agesHint')}</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {draftAges.map((age, index) => (
                <Select
                  key={index}
                  value={age === null ? '' : String(age)}
                  onValueChange={(next) => emit(value.adults, draftAges.map((current, i) => (i === index ? Number(next) : current)))}
                >
                  <SelectTrigger aria-label={t('guests.childAge', { number: index + 1 })} className="h-9">
                    <SelectValue placeholder={t('guests.agePlaceholder', { number: index + 1 })} />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: MAX_CHILD_AGE + 1 }, (_, years) => (
                      <SelectItem key={years} value={String(years)}>
                        {t('guests.age', { count: years })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ))}
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <Button size="sm" variant="primary" onClick={() => setOpen(false)}>
            {t('guests.done')}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function fitAges(ages: (number | null)[], children: number): (number | null)[] {
  return Array.from({ length: children }, (_, index) => ages[index] ?? null)
}
