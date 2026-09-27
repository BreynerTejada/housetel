import { useQueryClient } from '@tanstack/react-query'
import { Calculator, ChevronLeft, ChevronRight, Layers, SlidersHorizontal, Tags } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { DatePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty } from '@/lib/auth'
import { normalizeLang } from '@/lib/format'
import { useLocalStorageState } from '@/lib/hooks'
import { useCan } from '@/lib/permissions'
import { invalidatePrices, ratesKeys, useRateGrid, useRatesList, type BulkResult, type GridPlan, type RatePlan } from '../api'
import { BulkEditSheet } from '../components/BulkEditSheet'
import { QuoteSheet } from '../components/QuoteSheet'
import { RateGrid } from '../components/RateGrid'
import { SourceLegend } from '../components/SourceLegend'
import { UndoButton } from '../components/UndoControl'
import { useCellSave } from '../hooks/useCellSave'
import { useUndoStack } from '../hooks/useUndoStack'
import { addDays } from '../lib/grid-utils'
import { derivationLabel, pick } from '../lib/text'

const SPANS = [14, 30, 60, 90] as const
type Span = (typeof SPANS)[number]

/**
 * `/app/rates`: the rate grid of one plan (categories × nights), edited in place. It starts on the business
 * date of the active property (never the device date) and starts over when the property changes.
 */
export default function RatesGridPage() {
  const { property } = useActiveProperty()
  if (!property) return <LoadingState variant="rows" rows={8} />
  return <RatesGrid key={property.id} today={property.business_date} />
}

function RatesGrid({ today }: { today: string }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const canManage = useCan('rates.manage')

  const [start, setStart] = useState(today)
  const [storedSpan, setSpan] = useLocalStorageState<number>('housetel.rates.span', 14)
  const span: Span = (SPANS as readonly number[]).includes(storedSpan) ? (storedSpan as Span) : 14
  const [showRestrictions, setShowRestrictions] = useLocalStorageState('housetel.rates.restrictions', true)
  const [planId, setPlanId] = useState<string | null>(null)
  const end = addDays(start, span)

  const params = { start, end, planId, lang }
  const gridQuery = useRateGrid(params)
  const plansQuery = useRatesList<RatePlan>('rate-plans')
  const grid = gridQuery.data
  const plan = grid?.rate_plan ?? null
  const editable = canManage && Boolean(plan?.editable)

  const undo = useUndoStack({ onUndone: () => void invalidatePrices(queryClient) })
  const { save, pending } = useCellSave({ queryKey: ratesKeys.grid(params), planId: plan?.id ?? null, onSaved: undo.push })

  const [bulk, setBulk] = useState<{ open: boolean; preset: string[] | null }>({ open: false, preset: null })
  const [quoteOpen, setQuoteOpen] = useState(false)

  function bulkApplied(result: BulkResult) {
    setBulk({ open: false, preset: null })
    toast.success(t('bulk.done', { count: result.updated }))
    if (result.audit_event_id) undo.push(result.audit_event_id)
    void invalidatePrices(queryClient)
  }

  const plans = plansQuery.data ?? []
  const basePlans = plans.filter((item) => item.kind === 'base')
  const derivedPlans = plans.filter((item) => item.kind === 'derived')

  return (
    <div className="grid gap-4">
      <PageHeader
        title={t('grid.title')}
        description={t('grid.description')}
        actions={
          <>
            <Button onClick={() => setQuoteOpen(true)} disabled={plans.length === 0}>
              <Calculator aria-hidden />
              {t('quote.open')}
            </Button>
            {canManage && <UndoButton state={undo} />}
            {editable && (
              <Button variant="primary" onClick={() => setBulk({ open: true, preset: null })}>
                <SlidersHorizontal aria-hidden />
                {t('bulk.title')}
              </Button>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="grid gap-1.5">
          <Label htmlFor="rates-plan">{t('grid.plan')}</Label>
          <Select value={plan?.id ?? ''} onValueChange={(value) => setPlanId(value)} disabled={plans.length === 0}>
            <SelectTrigger id="rates-plan" className="w-64">
              <SelectValue placeholder={t('grid.choosePlan')} />
            </SelectTrigger>
            <SelectContent>
              {basePlans.length > 0 && (
                <SelectGroup>
                  <SelectLabel>{t('plans.kinds.base')}</SelectLabel>
                  {basePlans.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {pick(item.name, lang)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
              {derivedPlans.length > 0 && (
                <SelectGroup>
                  <SelectLabel>{t('plans.kinds.derived')}</SelectLabel>
                  {derivedPlans.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {pick(item.name, lang)} · {derivationLabel(item.derivation_type, item.derivation_value, grid?.currency, lang)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="rates-start">{t('grid.from')}</Label>
          <div className="flex items-center gap-1">
            <Button size="icon" aria-label={t('grid.previousWeek')} onClick={() => setStart(addDays(start, -7))}>
              <ChevronLeft aria-hidden />
            </Button>
            <DatePicker id="rates-start" value={start} onChange={(value) => value && setStart(value)} className="w-44" />
            <Button size="icon" aria-label={t('grid.nextWeek')} onClick={() => setStart(addDays(start, 7))}>
              <ChevronRight aria-hidden />
            </Button>
            <Button variant="ghost" onClick={() => setStart(today)} disabled={start === today}>
              {t('grid.today')}
            </Button>
          </div>
        </div>

        <ToggleGroup
          type="single"
          value={String(span)}
          onValueChange={(value) => value && setSpan(Number(value))}
          aria-label={t('grid.span')}
        >
          {SPANS.map((value) => (
            <ToggleGroupItem key={value} value={String(value)} className="px-2 whitespace-nowrap sm:px-2.5">
              {t('grid.spanNights', { count: value })}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <label className="flex h-9 items-center gap-2 text-[13px] font-semibold text-fg">
          <Switch checked={showRestrictions} onCheckedChange={setShowRestrictions} />
          {t('grid.showRestrictions')}
        </label>
      </div>

      {plan && plan.kind === 'derived' && (
        <DerivedNotice plan={plan} plans={plans} currency={grid?.currency ?? 'COP'} onOpenParent={setPlanId} />
      )}
      {undo.endpointMissing && <p className="text-xs text-muted">{t('undo.unavailable')}</p>}

      {gridQuery.isPending ? (
        <LoadingState variant="rows" rows={8} />
      ) : gridQuery.isError ? (
        <ErrorState error={gridQuery.error} onRetry={() => void gridQuery.refetch()} />
      ) : !grid || !plan ? (
        <EmptyState
          icon={Layers}
          title={t('grid.noPlans')}
          description={t('grid.noPlansHint')}
          action={
            canManage && (
              <Button asChild variant="primary">
                <Link to="/app/rates/plans">{t('grid.createPlan')}</Link>
              </Button>
            )
          }
        />
      ) : grid.room_types.length === 0 ? (
        <EmptyState
          icon={Tags}
          title={t('grid.noRoomTypes')}
          description={t('grid.noRoomTypesHint')}
          action={
            canManage && (
              <Button asChild>
                <Link to="/app/rates/plans">{t('grid.editPlans')}</Link>
              </Button>
            )
          }
        />
      ) : (
        <RateGrid
          grid={grid}
          today={today}
          editable={editable}
          showRestrictions={showRestrictions}
          pendingKeys={pending}
          onChange={save}
          onBulkEdit={(roomTypeId) => setBulk({ open: true, preset: [roomTypeId] })}
        />
      )}

      <SourceLegend />

      <QuoteSheet
        open={quoteOpen}
        onOpenChange={setQuoteOpen}
        plans={plans}
        planId={plan?.id ?? null}
        today={today}
        currency={grid?.currency ?? 'COP'}
      />

      {grid && plan && editable && (
        <BulkEditSheet
          open={bulk.open}
          onOpenChange={(open) => setBulk((current) => ({ ...current, open }))}
          planId={plan.id}
          planName={pick(plan.name, lang)}
          currency={grid.currency}
          roomTypes={grid.room_types}
          from={start}
          to={addDays(end, -1)}
          preset={bulk.preset}
          onApplied={bulkApplied}
        />
      )}
    </div>
  )
}

function DerivedNotice({
  plan,
  plans,
  currency,
  onOpenParent,
}: {
  plan: GridPlan
  plans: RatePlan[]
  currency: string
  onOpenParent: (id: string) => void
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const parent = plans.find((item) => item.id === plan.parent)
  return (
    <div role="note" className="flex flex-wrap items-center gap-3 rounded-lg border border-info/25 bg-info-soft px-4 py-3 text-sm text-info-ink">
      <p className="min-w-0 flex-1">
        {t('grid.derivedNotice', {
          parent: parent ? pick(parent.name, lang) : t('grid.itsBasePlan'),
          rule: derivationLabel(plan.derivation_type, plan.derivation_value, currency, lang),
        })}
      </p>
      {parent && (
        <Button size="sm" variant="secondary" onClick={() => onOpenParent(parent.id)}>
          {t('grid.openParent')}
        </Button>
      )}
    </div>
  )
}
