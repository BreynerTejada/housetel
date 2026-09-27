import { useQueryClient } from '@tanstack/react-query'
import { CalendarRange, Pencil, Plus } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { invalidatePrices, postSeasonRate, useDeleteResource, useHolidays, useRatesList, type RatePlan, type Season } from '../../api'
import { useAdjustmentSummary } from '../../hooks/useAdjustmentSummary'
import { soldRoomTypes, type PlansData } from '../../hooks/usePlansData'
import { parseDecimal } from '../../lib/forms'
import { applyPercent, signedPercent } from '../../lib/plans'
import { pick } from '../../lib/text'
import { RowActions } from '../crud'
import { SeasonRateDialog, type SeasonRateTarget } from './PriceDialogs'
import { SeasonDialog } from './SeasonDialog'
import { YearCalendar } from './YearCalendar'

/** Tab "Temporadas": seasons on a year calendar and the price of every category during the selected one. */
export function SeasonsPanel({ data, currency, today }: { data: PlansData; currency: string; today: string }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const seasonsQuery = useRatesList<Season>('seasons')
  const remove = useDeleteResource('seasons')
  const [year, setYear] = useState(() => Number(today.slice(0, 4)))
  const holidays = useHolidays(year, lang)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [dialog, setDialog] = useState<{ open: boolean; season: Season | null; key: number }>({ open: false, season: null, key: 0 })

  if (seasonsQuery.isPending || data.isPending) return <LoadingState variant="rows" rows={6} />
  if (seasonsQuery.isError) return <ErrorState error={seasonsQuery.error} onRetry={() => void seasonsQuery.refetch()} />
  if (data.error) return <ErrorState error={data.error} onRetry={data.refetch} />

  const seasons = seasonsQuery.data
  const selected = seasons.find((season) => season.id === selectedId) ?? seasons[0] ?? null
  const openDialog = (season: Season | null) => setDialog((current) => ({ open: true, season, key: current.key + 1 }))

  function select(season: Season) {
    setSelectedId(season.id)
    const startYear = Number(season.start_date.slice(0, 4))
    const endYear = Number(season.end_date.slice(0, 4))
    if (year < startYear || year > endYear) setYear(startYear)
  }

  return (
    <div className="grid gap-5">
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(16rem,20rem)_1fr]">
        <section aria-labelledby="seasons-title" className="rounded-lg border border-border bg-surface shadow-xs">
          <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
            <h3 id="seasons-title" className="text-[15px] font-bold tracking-[-0.01em] text-fg">
              {t('plans.seasons.title')}
            </h3>
            {canManage && (
              <Button size="sm" variant="primary" onClick={() => openDialog(null)}>
                <Plus aria-hidden />
                {t('plans.seasons.new')}
              </Button>
            )}
          </div>
          {seasons.length === 0 ? (
            <EmptyState icon={CalendarRange} title={t('plans.seasons.empty')} description={t('plans.seasons.emptyHint')} />
          ) : (
            <ul className="grid gap-1 p-2">
              {seasons.map((season) => {
                const isSelected = season.id === selected?.id
                return (
                  <li
                    key={season.id}
                    className={cn(
                      'flex items-center gap-1 rounded-md border border-transparent pr-1 transition-colors',
                      isSelected ? 'border-border bg-surface-2' : 'hover:bg-surface-2/60',
                    )}
                  >
                    <button
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => select(season)}
                      className="flex min-w-0 flex-1 items-start gap-3 rounded-md px-2.5 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      <span aria-hidden className="mt-1 h-8 w-1.5 shrink-0 rounded-full" style={{ background: season.color }} />
                      <span className="grid min-w-0">
                        <span className="truncate text-[13px] font-bold text-fg">{season.name}</span>
                        <span className="num text-xs text-muted">{formatDateRange(season.start_date, season.end_date, lang)}</span>
                        <span className="text-2xs font-semibold tracking-wide text-subtle">
                          {t('plans.seasons.priorityValue', { value: season.priority })} ·{' '}
                          {t('plans.seasons.pricesCount', { count: season.rates.length })}
                        </span>
                      </span>
                    </button>
                    {canManage && (
                      <RowActions
                        name={season.name}
                        onEdit={() => openDialog(season)}
                        onDelete={async () => {
                          await remove.mutateAsync(season.id)
                          toast.success(t('plans.seasons.deleted'))
                        }}
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <YearCalendar
          year={year}
          onYearChange={setYear}
          seasons={seasons}
          holidays={holidays.data ?? []}
          selectedId={selected?.id ?? null}
          today={today}
        />
      </div>

      {selected && <SeasonPrices season={selected} data={data} currency={currency} canManage={canManage} />}

      {dialog.key > 0 && (
        <SeasonDialog
          key={dialog.key}
          open={dialog.open}
          onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
          season={dialog.season}
          today={today}
          usedColors={seasons.map((season) => season.color)}
          onSaved={select}
        />
      )}
    </div>
  )
}

function SeasonPrices({ season, data, currency, canManage }: { season: Season; data: PlansData; currency: string; canManage: boolean }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const summary = useAdjustmentSummary()
  const [planId, setPlanId] = useState<string | null>(null)
  const [dialog, setDialog] = useState<{ open: boolean; target: SeasonRateTarget | null; key: number }>({ open: false, target: null, key: 0 })

  if (data.basePlans.length === 0) {
    return <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">{t('plans.seasons.noBasePlan')}</p>
  }
  const plan = data.basePlans.find((item) => item.id === planId) ?? data.basePlans[0]
  const planName = pick(plan.name, lang)
  const roomTypes = soldRoomTypes(plan, data.roomTypes)
  const headingId = `season-prices-${season.id}`

  return (
    <section aria-labelledby={headingId} className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <div className="flex flex-wrap items-end justify-between gap-3 px-4 pt-4 pb-3">
        <div className="grid gap-0.5">
          <p className="eyebrow">{t('plans.seasons.pricesEyebrow')}</p>
          <h3 id={headingId} className="flex items-center gap-2 text-[15px] font-bold tracking-[-0.01em] text-fg">
            <span aria-hidden className="size-2.5 rounded-full" style={{ background: season.color }} />
            {season.name}
          </h3>
          <p className="text-xs text-muted">{t('plans.seasons.pricesHint')}</p>
        </div>
        {data.basePlans.length > 1 && (
          <div className="grid gap-1.5">
            <Label htmlFor={`${headingId}-plan`}>{t('plans.editor.parent')}</Label>
            <Select name={`${headingId}-plan`} value={plan.id} onValueChange={setPlanId}>
              <SelectTrigger id={`${headingId}-plan`} className="w-60">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.basePlans.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {pick(item.name, lang)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
      <div className="border-t border-border">
        <Table aria-label={t('plans.seasons.tableLabel', { season: season.name, plan: planName })} className="num text-[13px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">{t('plans.families.roomType')}</TableHead>
              <TableHead className="text-right">{t('plans.seasons.defaultPrice')}</TableHead>
              <TableHead className="text-right">{t('plans.seasons.seasonPrice')}</TableHead>
              <TableHead className="text-right">{t('plans.seasons.difference')}</TableHead>
              <TableHead>{t('plans.defaults.byWeekday')}</TableHead>
              <TableHead>
                <span className="sr-only">{t('crud.actions')}</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {roomTypes.map((roomType) => {
              const defaults = data.defaultsFor(roomType.id, plan.id)
              const rate = season.rates.find((item) => item.room_type === roomType.id && item.rate_plan === plan.id) ?? null
              const name = pick(roomType.name, lang)
              const difference =
                rate && defaults && Number(defaults.price) > 0
                  ? Math.round((Number(rate.price) / Number(defaults.price) - 1) * 1000) / 10
                  : null
              const target: SeasonRateTarget = { season, roomType, plan, rate, defaults }
              return (
                <TableRow key={roomType.id}>
                  <TableHead scope="row" className="h-auto py-2.5 pl-4 font-normal">
                    <span className="flex items-center gap-2.5">
                      <span aria-hidden className="h-6 w-1 shrink-0 rounded-full" style={{ background: roomType.color }} />
                      <span className="text-[13px] font-semibold text-fg">{name}</span>
                    </span>
                  </TableHead>
                  <TableCell className="text-right">
                    {defaults ? <MoneyText value={defaults.price} currency={currency} /> : <span className="text-warning-ink">{t('plans.families.noPrice')}</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    {rate ? (
                      <MoneyText value={rate.price} currency={currency} className="text-[14px] font-bold text-fg" />
                    ) : (
                      <span className="text-xs text-muted">{t('plans.seasons.followsDefault')}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {difference === null ? (
                      <span className="text-subtle">—</span>
                    ) : (
                      <span className={cn('font-semibold', difference >= 0 ? 'text-accent-ink' : 'text-success-ink')}>
                        {signedPercent(difference, lang)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted">{rate ? summary(rate.dow_adjustments) : '—'}</TableCell>
                  <TableCell className="text-right">
                    {canManage &&
                      (rate ? (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t('plans.seasons.editRateFor', { roomType: name })}
                          onClick={() => setDialog((current) => ({ open: true, target, key: current.key + 1 }))}
                        >
                          <Pencil aria-hidden />
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          aria-label={t('plans.seasons.setRateFor', { roomType: name })}
                          onClick={() => setDialog((current) => ({ open: true, target, key: current.key + 1 }))}
                        >
                          {t('plans.defaults.set')}
                        </Button>
                      ))}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
      {canManage && roomTypes.length > 0 && <ComputeFromDefaults season={season} plan={plan} data={data} currency={currency} />}
      {dialog.target && (
        <SeasonRateDialog
          key={dialog.key}
          open={dialog.open}
          onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
          target={dialog.target}
          currency={currency}
        />
      )}
    </section>
  )
}

/** "Default price + N %" for every category of the plan (creates or replaces the season prices). */
function ComputeFromDefaults({ season, plan, data, currency }: { season: Season; plan: RatePlan; data: PlansData; currency: string }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const id = useId()
  const [percent, setPercent] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = parseDecimal(percent)
    if (value === null || Number(value) < -100 || Number(value) > 1000) {
      setError(t('plans.adjustmentInvalid'))
      return
    }
    setError(null)
    setMessage(null)
    const roomTypes = soldRoomTypes(plan, data.roomTypes)
    const priced = roomTypes.filter((roomType) => data.defaultsFor(roomType.id, plan.id))
    const missing = roomTypes.filter((roomType) => !data.defaultsFor(roomType.id, plan.id))
    setPending(true)
    try {
      for (const roomType of priced) {
        const defaults = data.defaultsFor(roomType.id, plan.id)!
        await postSeasonRate({
          season: season.id,
          room_type: roomType.id,
          rate_plan: plan.id,
          price: String(applyPercent(defaults.price, value, currency)),
          dow_adjustments: { ...defaults.dow_adjustments },
        })
      }
      if (priced.length > 0) toast.success(t('plans.seasons.computed', { count: priced.length }))
      if (missing.length > 0) {
        setMessage(t('plans.seasons.missingDefaults', { count: missing.length, names: missing.map((item) => pick(item.name, lang)).join(', ') }))
      }
    } catch (failure) {
      setError(errorMessage(failure, t))
    } finally {
      setPending(false)
      await queryClient.invalidateQueries({ queryKey: ['rates', 'seasons'] })
      void invalidatePrices(queryClient)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-2 border-t border-border bg-surface-2/50 px-4 py-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-percent`}>{t('plans.seasons.computeLabel')}</Label>
          <Input
            id={`${id}-percent`}
            inputMode="decimal"
            autoComplete="off"
            value={percent}
            onChange={(event) => setPercent(event.target.value)}
            placeholder="30"
            aria-invalid={Boolean(error)}
            className="num w-28 text-right"
          />
        </div>
        <Button type="submit" loading={pending} disabled={!percent.trim()}>
          {t('plans.seasons.compute')}
        </Button>
        <p className="min-w-0 flex-1 text-xs text-muted">{t('plans.seasons.computeHint')}</p>
      </div>
      {error && (
        <p role="alert" className="text-xs font-medium text-danger-ink">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="text-xs font-medium text-warning-ink">
          {message}
        </p>
      )}
    </form>
  )
}
