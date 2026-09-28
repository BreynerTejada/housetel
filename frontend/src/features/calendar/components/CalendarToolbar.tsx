import { ChevronDown, ChevronLeft, ChevronRight, CornerDownRight, ListFilter, LoaderCircle, Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { DatePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { fieldBase } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CalRoomType, StayStatus } from '../api'
import { SPANS, STATUSES } from '../lib/constants'
import { addDays } from '../lib/dates'
import { pick } from '../lib/labels'

export interface CalendarToolbarProps {
  start: string
  /** First day shown by "Today" (the day before the business date). */
  homeStart: string
  span: number
  onStart: (value: string) => void
  onSpan: (value: number) => void
  roomTypes: readonly CalRoomType[]
  /** Chosen categories; empty = all. */
  categories: ReadonlySet<string>
  onCategories: (next: Set<string>) => void
  /** Chosen statuses; all four by default. */
  statuses: ReadonlySet<StayStatus>
  onStatuses: (next: Set<StayStatus>) => void
  search: string
  onSearch: (value: string) => void
  matchCount: number
  onNextMatch: () => void
  refreshing: boolean
}

/** Toggles `value` in a multi-choice filter, never leaving it empty (an empty choice would hide everything). */
function toggled<T>(current: ReadonlySet<T>, all: readonly T[], value: T): Set<T> {
  const base = current.size === 0 ? new Set(all) : new Set(current)
  if (base.has(value)) {
    if (base.size > 1) base.delete(value)
  } else {
    base.add(value)
  }
  return base
}

export function CalendarToolbar(props: CalendarToolbarProps) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const { start, homeStart, span, roomTypes, categories, statuses, search, matchCount, refreshing } = props
  const categoryIds = roomTypes.map((roomType) => roomType.id)
  const allCategories = categories.size === 0 || categories.size === categoryIds.length
  const allStatuses = statuses.size === STATUSES.length

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2.5">
      <div className="flex items-center gap-1" role="group" aria-label={t('toolbar.from')}>
        <Button size="icon" aria-label={t('toolbar.previous')} onClick={() => props.onStart(addDays(start, -7))}>
          <ChevronLeft aria-hidden />
        </Button>
        <DatePicker
          value={start}
          onChange={(value) => value && props.onStart(value)}
          aria-label={t('toolbar.from')}
          className="w-[10.5rem]"
        />
        <Button size="icon" aria-label={t('toolbar.next')} onClick={() => props.onStart(addDays(start, 7))}>
          <ChevronRight aria-hidden />
        </Button>
        <Button variant="ghost" onClick={() => props.onStart(homeStart)} disabled={start === homeStart}>
          {t('toolbar.today')}
        </Button>
      </div>

      <ToggleGroup type="single" value={String(span)} onValueChange={(value) => value && props.onSpan(Number(value))} aria-label={t('toolbar.span')}>
        {SPANS.map((value) => (
          <ToggleGroupItem key={value} value={String(value)} className="px-2 whitespace-nowrap sm:px-2.5">
            {t('toolbar.spanDays', { count: value })}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <div className="flex items-center gap-1.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant={allCategories ? 'secondary' : 'subtle'}>
              <ListFilter aria-hidden />
              {t('toolbar.categories')}:{' '}
              <span className={cn('font-bold', !allCategories && 'text-accent-ink')}>
                {allCategories ? t('toolbar.allCategories') : t('toolbar.someCategories', { count: categories.size, total: categoryIds.length })}
              </span>
              <ChevronDown aria-hidden className="text-muted" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-60">
            <DropdownMenuCheckboxItem checked={allCategories} onSelect={(event) => event.preventDefault()} onCheckedChange={() => props.onCategories(new Set())}>
              {t('toolbar.allCategories')}
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            {roomTypes.map((roomType) => (
              <DropdownMenuCheckboxItem
                key={roomType.id}
                checked={allCategories || categories.has(roomType.id)}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={() => {
                  const next = toggled(categories, categoryIds, roomType.id)
                  props.onCategories(next.size === categoryIds.length ? new Set() : next)
                }}
              >
                <span aria-hidden className="size-2.5 shrink-0 rounded-[3px]" style={{ background: roomType.color }} />
                <span className="truncate">{pick(roomType.name, lang)}</span>
                <span className="num ml-auto text-2xs font-bold tracking-wide text-subtle">{roomType.code}</span>
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant={allStatuses ? 'secondary' : 'subtle'}>
              {t('toolbar.statuses')}:{' '}
              <span className={cn('font-bold', !allStatuses && 'text-accent-ink')}>
                {allStatuses ? t('toolbar.allStatuses') : t('toolbar.someStatuses', { count: statuses.size, total: STATUSES.length })}
              </span>
              <ChevronDown aria-hidden className="text-muted" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-52">
            <DropdownMenuLabel>{t('toolbar.statuses')}</DropdownMenuLabel>
            {STATUSES.map((status) => (
              <DropdownMenuCheckboxItem
                key={status}
                checked={statuses.has(status)}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={() => props.onStatuses(toggled(statuses, STATUSES, status))}
              >
                <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: `var(--status-${status.replace('_', '-')})` }} />
                {t(`status.reservation.${status}`, { ns: 'common' })}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
        <label className={cn(fieldBase, 'flex h-8 min-w-0 flex-1 items-center gap-2 px-2.5 sm:w-60 sm:flex-none')}>
          <Search aria-hidden className="size-3.5 shrink-0 text-muted" />
          <input
            type="search"
            name="calendar-search"
            value={search}
            onChange={(event) => props.onSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                props.onNextMatch()
              } else if (event.key === 'Escape' && search) {
                event.preventDefault()
                props.onSearch('')
              }
            }}
            placeholder={t('toolbar.search')}
            aria-label={t('toolbar.searchLabel')}
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-[13px] outline-none [&::-webkit-search-cancel-button]:hidden"
          />
          {search && (
            <button
              type="button"
              aria-label={t('toolbar.clearSearch')}
              onClick={() => props.onSearch('')}
              className="grid size-5 shrink-0 place-items-center rounded text-muted hover:text-fg"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          )}
        </label>
        {search.trim() && (
          <>
            <span role="status" className="shrink-0 text-xs font-semibold whitespace-nowrap text-muted">
              {t('toolbar.matches', { count: matchCount })}
            </span>
            {matchCount > 0 && (
              <Button size="icon-sm" variant="ghost" aria-label={t('toolbar.nextMatch')} onClick={props.onNextMatch}>
                <CornerDownRight aria-hidden />
              </Button>
            )}
          </>
        )}
      </div>

      {refreshing && (
        <span role="status" className="flex items-center gap-1.5 text-xs text-muted">
          <LoaderCircle aria-hidden className="size-3.5 animate-spin text-accent" />
          {t('toolbar.refreshing')}
        </span>
      )}
    </div>
  )
}
