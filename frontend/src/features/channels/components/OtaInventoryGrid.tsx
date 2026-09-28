import { Ban, LogIn, LogOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { OtaCell, OtaInventory, OtaRate, OtaRoom } from '../api'
import { cellSignature, cellState } from '../lib/channels'
import { tr } from '../lib/text'
import './ota.css'

const FLASH_MS = 2600

export interface OtaCellPick {
  room: OtaRoom
  rate: OtaRate
  date: string
  cell: OtaCell
}

function cellKey(room: string, rate: string, date: string) {
  return `${room}|${rate}|${date}`
}

function isWeekendNight(date: string): boolean {
  const day = new Date(`${date}T12:00:00`).getDay()
  return day === 5 || day === 6
}

/**
 * What the OTA holds, as its extranet would show it: per channel room, the units it can sell and, per channel
 * rate, the price and restrictions of every night. Cells that a new push just changed glow for a moment, so
 * the ARI can be seen arriving. An open night can be clicked to book it in the OTA.
 */
export function OtaInventoryGrid({
  inventory,
  today,
  onPick,
}: {
  inventory: OtaInventory
  /** Business date of the property (`YYYY-MM-DD`). */
  today: string
  onPick?: (pick: OtaCellPick) => void
}) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const currency = inventory.currency
  const flash = useChangedCells(inventory)

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface" role="region" aria-label={t('ota.gridLabel')} tabIndex={0}>
      <table className="w-full border-separate border-spacing-0 text-sm">
        <caption className="sr-only">{t('ota.gridCaption', { ota: inventory.connection.ota })}</caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky left-0 z-20 w-32 min-w-32 border-r border-b border-border bg-surface px-2 text-left align-bottom sm:w-56 sm:min-w-56 sm:px-3"
            >
              <span className="eyebrow block pb-2">{t('ota.roomsAndRates')}</span>
            </th>
            {inventory.dates.map((date, index) => {
              const isToday = date === today
              const showMonth = index === 0 || date.endsWith('-01')
              return (
                <th
                  key={date}
                  scope="col"
                  aria-label={formatDate(date, 'EEEE d MMMM', lang)}
                  className={cn(
                    'h-12 min-w-[5.25rem] border-b border-border bg-surface px-2 text-right align-bottom font-normal',
                    isWeekendNight(date) && 'bg-surface-2',
                    isToday && 'shadow-[inset_0_3px_0_var(--accent)]',
                  )}
                >
                  <span className={cn('eyebrow block', isToday && 'text-accent-ink')}>{formatDate(date, 'EEE', lang)}</span>
                  <span className="flex items-baseline justify-end gap-1 pb-1">
                    {showMonth && <span className="text-2xs font-semibold text-muted uppercase">{formatDate(date, 'MMM', lang)}</span>}
                    <span className={cn('text-[15px] leading-5 font-bold', isToday ? 'text-accent-ink' : 'text-fg')}>{formatDate(date, 'd', lang)}</span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        {inventory.rooms.map((room) => {
          const name = tr(room.room_type.name, lang) || room.room_type.code
          const units = room.rates[0]?.cells ?? []
          return (
            <tbody key={room.external_room_id}>
              <tr>
                <th scope="row" className="sticky left-0 z-10 border-t border-r border-border bg-bg px-2 py-2 text-left sm:px-3">
                  <span className="flex items-center gap-2">
                    <span aria-hidden className="h-8 w-1 shrink-0 rounded-full" style={{ background: room.room_type.color }} />
                    <span className="min-w-0">
                      <span className="num block truncate text-[13px] font-bold text-fg">{room.external_room_id}</span>
                      <span className="block truncate text-2xs font-semibold text-muted">
                        {name}
                        <span className="hidden sm:inline"> · {room.room_type.kind === 'dorm' ? t('ota.bedsLeft') : t('ota.roomsLeft')}</span>
                      </span>
                    </span>
                  </span>
                </th>
                {inventory.dates.map((date, index) => {
                  const cell = units[index] ?? null
                  const changed = flash.has(cellKey(room.external_room_id, '#units', date))
                  return (
                    <td
                      key={date}
                      className={cn('border-t border-border bg-bg px-2 text-right align-middle', isWeekendNight(date) && 'bg-surface-2/70')}
                    >
                      <span
                        data-changed={changed || undefined}
                        className={cn(
                          'ota-flash num inline-block rounded px-1.5 py-0.5 text-[13px] font-semibold',
                          !cell ? 'text-subtle' : cell.available <= 0 ? 'bg-danger-soft text-danger-ink' : cell.available <= 1 ? 'text-warning-ink' : 'text-fg',
                        )}
                        aria-label={cell ? t('ota.unitsCell', { count: Math.max(cell.available, 0), date }) : t('ota.noData')}
                      >
                        {cell ? Math.max(cell.available, 0) : '—'}
                      </span>
                    </td>
                  )
                })}
              </tr>
              {room.rates.map((rate) => {
                const planName = rate.rate_plan ? tr(rate.rate_plan.name, lang) || rate.rate_plan.code : t('ota.noPlan')
                return (
                  <tr key={rate.external_rate_id || 'none'}>
                    <th scope="row" className="sticky left-0 z-10 border-r border-border bg-surface py-1.5 pr-2 pl-5 text-left sm:pr-3 sm:pl-6">
                      <span className="num block truncate text-xs font-semibold text-fg">{rate.external_rate_id || t('ota.availabilityOnly')}</span>
                      <span className="block truncate text-2xs text-muted">
                        {planName}
                        {Number(rate.markup_percent) !== 0 && ` · ${Number(rate.markup_percent) > 0 ? '+' : ''}${Number(rate.markup_percent)} %`}
                      </span>
                    </th>
                    {inventory.dates.map((date, index) => {
                      const cell = rate.cells[index] ?? null
                      const state = cellState(cell)
                      const changed = flash.has(cellKey(room.external_room_id, rate.external_rate_id, date))
                      const pickable = Boolean(onPick && cell && state === 'open' && date >= today)
                      const label = describeCell(t, cell, state, planName, date, currency)
                      const content = (
                        <>
                          {cell && (cell.min_los || cell.closed_to_arrival || cell.closed_to_departure) ? (
                            <span className="flex items-center justify-end gap-0.5 text-2xs leading-3 font-semibold text-info-ink">
                              {cell.min_los ? <span className="num">{t('ota.minLosShort', { count: cell.min_los })}</span> : null}
                              {cell.closed_to_arrival && <LogIn aria-hidden className="size-3" />}
                              {cell.closed_to_departure && <LogOut aria-hidden className="size-3" />}
                            </span>
                          ) : null}
                          <span
                            className={cn(
                              'num block text-[13px] leading-5 font-semibold',
                              state === 'open' && 'text-fg',
                              state === 'soldout' && 'text-muted line-through decoration-danger/60',
                              state === 'closed' && 'text-danger-ink',
                              state === 'missing' && 'text-subtle',
                            )}
                          >
                            {state === 'missing' ? '—' : state === 'closed' ? <Ban aria-hidden className="ml-auto size-3.5" /> : formatMoney(cell?.price, currency)}
                          </span>
                        </>
                      )
                      return (
                        <td
                          key={date}
                          className={cn(
                            'border-t border-border/60 p-0 text-right align-middle',
                            isWeekendNight(date) && 'bg-surface-2/50',
                            (state === 'closed' || state === 'missing') && 'hatch',
                          )}
                        >
                          {pickable ? (
                            <button
                              type="button"
                              data-changed={changed || undefined}
                              aria-label={t('ota.bookCell', { cell: label })}
                              onClick={() => cell && onPick?.({ room, rate, date, cell })}
                              className="ota-flash block h-full min-h-11 w-full px-2 py-1 text-right transition-colors hover:bg-accent-soft/60 focus-visible:bg-accent-soft/60 focus-visible:shadow-[inset_0_0_0_2px_var(--accent)] focus-visible:outline-none"
                            >
                              {content}
                            </button>
                          ) : (
                            <span data-changed={changed || undefined} aria-label={label} className="ota-flash block min-h-11 px-2 py-1">
                              {content}
                            </span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          )
        })}
      </table>
    </div>
  )
}

function describeCell(
  t: (key: string, options?: Record<string, unknown>) => string,
  cell: OtaCell | null,
  state: ReturnType<typeof cellState>,
  plan: string,
  date: string,
  currency: string,
): string {
  if (!cell || state === 'missing') return t('ota.cellMissing', { plan, date })
  if (state === 'closed') return t('ota.cellClosed', { plan, date })
  const parts = [t('ota.cellPrice', { plan, date, price: formatMoney(cell.price, currency) })]
  if (state === 'soldout') parts.push(t('ota.soldOut'))
  if (cell.min_los) parts.push(t('ota.minLos', { count: cell.min_los }))
  if (cell.closed_to_arrival) parts.push(t('ota.cta'))
  if (cell.closed_to_departure) parts.push(t('ota.ctd'))
  return parts.join(' · ')
}

/**
 * Keys of the cells whose values changed since the previous fetch of the same nights (units under
 * `room|#units|date`). The set lives for a couple of seconds, long enough for the glow animation.
 */
function useChangedCells(inventory: OtaInventory): Set<string> {
  const previous = useRef<Map<string, string> | null>(null)
  const [flash, setFlash] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    const current = new Map<string, string>()
    for (const room of inventory.rooms) {
      room.rates[0]?.cells.forEach((cell, index) => {
        current.set(cellKey(room.external_room_id, '#units', inventory.dates[index]), String(cell?.available ?? '-'))
      })
      for (const rate of room.rates) {
        rate.cells.forEach((cell, index) => {
          current.set(cellKey(room.external_room_id, rate.external_rate_id, inventory.dates[index]), cellSignature(cell))
        })
      }
    }
    const before = previous.current
    previous.current = current
    if (!before) return
    const changed = new Set<string>()
    for (const [key, signature] of current) {
      const old = before.get(key)
      if (old !== undefined && old !== signature) changed.add(key)
    }
    if (!changed.size) return
    // No cleanup on purpose: a newer flash replaces this one, and the late reset only clears its own set.
    setTimeout(() => setFlash(changed), 0)
    setTimeout(() => setFlash((current) => (current === changed ? new Set() : current)), FLASH_MS)
  }, [inventory])

  return flash
}
