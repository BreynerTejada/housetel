import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { formatMoney, formatNumber, formatPercent, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { TodayBoard } from '../api'

type MeterTone = 'accent' | 'success'

const FILL: Record<MeterTone, string> = { accent: 'bg-accent', success: 'bg-success' }
const TRACK: Record<MeterTone, string> = { accent: 'bg-accent-soft', success: 'bg-success-soft' }

/**
 * The day in five figures (plan C1 KPIs): occupancy tonight, arrivals and departures done of their total,
 * guests in house and today's revenue. Done-of-total figures are meters in the color of the state they lead
 * to (in house → terracotta, checked out → sage), each track a lighter step of its own hue.
 */
export function TodayFigures({ board }: { board: TodayBoard }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const { kpis, previous, currency } = board
  const arrivalsLeft = Math.max(0, kpis.arrivals_total - kpis.arrivals_done)
  const departuresLeft = Math.max(0, kpis.departures_total - kpis.departures_done)

  return (
    <section
      aria-label={t('today.figures')}
      className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border shadow-xs lg:grid-cols-5"
    >
      <Figure
        label={t('today.occupancy')}
        value={formatPercent(kpis.occupancy_pct, 1, lang)}
        meter={{ value: kpis.rooms_occupied, max: kpis.rooms_available, tone: 'accent', label: t('today.occupancyMeter', { done: kpis.rooms_occupied, total: kpis.rooms_available }) }}
        sub={t('today.roomsOf', { done: kpis.rooms_occupied, total: kpis.rooms_available })}
        delta={
          previous?.occupancy_pct != null
            ? { value: kpis.occupancy_pct - previous.occupancy_pct, text: t('today.points', { value: formatNumber(Math.abs(kpis.occupancy_pct - previous.occupancy_pct), lang, 1) }) }
            : undefined
        }
      />
      <Figure
        label={t('today.arrivals')}
        value={<DoneOf done={kpis.arrivals_done} total={kpis.arrivals_total} />}
        meter={{ value: kpis.arrivals_done, max: kpis.arrivals_total, tone: 'accent', label: t('today.arrivalsMeter', { done: kpis.arrivals_done, total: kpis.arrivals_total }) }}
        sub={
          kpis.arrivals_late > 0 ? (
            <span className="text-danger-ink">{t('today.late', { count: kpis.arrivals_late })}</span>
          ) : (
            t('today.toArrive', { count: arrivalsLeft })
          )
        }
      />
      <Figure
        label={t('today.departures')}
        value={<DoneOf done={kpis.departures_done} total={kpis.departures_total} />}
        meter={{ value: kpis.departures_done, max: kpis.departures_total, tone: 'success', label: t('today.departuresMeter', { done: kpis.departures_done, total: kpis.departures_total }) }}
        sub={
          kpis.departures_overdue > 0 ? (
            <span className="text-danger-ink">{t('today.overdue', { count: kpis.departures_overdue })}</span>
          ) : (
            t('today.toLeave', { count: departuresLeft })
          )
        }
      />
      <Figure label={t('today.inHouse')} value={formatNumber(kpis.in_house, lang)} sub={t('today.guestsInHouse', { count: kpis.guests_in_house })} />
      <Figure
        label={t('today.revenue')}
        value={formatMoney(kpis.revenue_today, currency)}
        sub={t('today.adr', { amount: formatMoney(kpis.adr_today, currency) })}
        delta={
          previous?.revenue != null
            ? { value: Number(kpis.revenue_today) - Number(previous.revenue), text: formatMoney(Math.abs(Number(kpis.revenue_today) - Number(previous.revenue)), currency) }
            : undefined
        }
        className="col-span-2 lg:col-span-1"
      />
    </section>
  )
}

function DoneOf({ done, total }: { done: number; total: number }) {
  const { t } = useTranslation('frontdesk')
  return (
    <>
      {done}
      <span className="ml-1.5 text-base font-semibold text-muted">{t('today.of', { total })}</span>
    </>
  )
}

function Figure({
  label,
  value,
  sub,
  meter,
  delta,
  className,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  meter?: { value: number; max: number; tone: MeterTone; label: string }
  delta?: { value: number; text: string }
  className?: string
}) {
  const { t } = useTranslation('frontdesk')
  const ratio = meter && meter.max > 0 ? Math.min(1, Math.max(0, meter.value / meter.max)) : 0
  const direction = !delta || Math.abs(delta.value) < 0.05 ? 'flat' : delta.value > 0 ? 'up' : 'down'
  const Arrow = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus

  return (
    <div
      className={cn('flex min-w-0 flex-col gap-2 bg-surface p-4', className)}
    >
      <p className="text-[13px] font-semibold text-muted">{label}</p>
      <p className="truncate text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">{value}</p>
      {meter && (
        <div
          role="meter"
          aria-label={meter.label}
          aria-valuemin={0}
          aria-valuemax={meter.max}
          aria-valuenow={meter.value}
          className={cn('h-1.5 overflow-hidden rounded-full', TRACK[meter.tone])}
        >
          <div className={cn('h-full rounded-full transition-[width] duration-500', FILL[meter.tone])} style={{ width: `${ratio * 100}%` }} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] text-muted">
        {sub && <span className="num">{sub}</span>}
        {delta && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 font-semibold',
              direction === 'up' ? 'text-success-ink' : direction === 'down' ? 'text-danger-ink' : 'text-muted',
            )}
          >
            <Arrow aria-hidden className="size-3.5" />
            <span className="num">{direction === 'flat' ? t('today.flat') : delta.text}</span>
            <span className="font-medium text-muted">{t('today.vsYesterday')}</span>
          </span>
        )}
      </div>
    </div>
  )
}
