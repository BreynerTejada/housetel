import { Layers, Pencil } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useAdjustmentSummary } from '../../hooks/useAdjustmentSummary'
import { soldRoomTypes, type PlansData } from '../../hooks/usePlansData'
import { pick } from '../../lib/text'
import { DefaultsDialog, type DefaultsTarget } from './PriceDialogs'

/** Tab "Precios por defecto": what each category of a base plan costs when no season or manual price applies. */
export function DefaultsPanel({ data, currency }: { data: PlansData; currency: string }) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('rates.manage')
  const summary = useAdjustmentSummary()
  const [planId, setPlanId] = useState<string | null>(null)
  const [dialog, setDialog] = useState<{ open: boolean; target: DefaultsTarget | null; key: number }>({ open: false, target: null, key: 0 })

  if (data.isPending) return <LoadingState variant="rows" rows={6} />
  if (data.error) return <ErrorState error={data.error} onRetry={data.refetch} />
  if (data.basePlans.length === 0) {
    return <EmptyState icon={Layers} title={t('grid.noPlans')} description={t('plans.families.emptyHint')} />
  }

  const plan = data.basePlans.find((item) => item.id === planId) ?? data.basePlans[0]
  const planName = pick(plan.name, lang)
  const roomTypes = soldRoomTypes(plan, data.roomTypes)
  const open = (target: DefaultsTarget) => setDialog((current) => ({ open: true, target, key: current.key + 1 }))

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-muted">{t('plans.defaults.intro')}</p>
        {data.basePlans.length > 1 && (
          <div className="grid gap-1.5">
            <Label htmlFor="defaults-plan">{t('plans.editor.parent')}</Label>
            <Select name="defaults-plan" value={plan.id} onValueChange={setPlanId}>
              <SelectTrigger id="defaults-plan" className="w-60">
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

      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
        <Table aria-label={t('plans.defaults.tableLabel', { plan: planName })} className="num text-[13px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>{t('plans.families.roomType')}</TableHead>
              <TableHead className="text-right">{t('plans.pricePerNight')}</TableHead>
              <TableHead>{t('plans.defaults.byWeekday')}</TableHead>
              <TableHead className="text-right">{t('plans.defaults.extraAdult')}</TableHead>
              <TableHead className="text-right">{t('plans.defaults.extraChild')}</TableHead>
              <TableHead className="text-right">{t('plans.defaults.single')}</TableHead>
              <TableHead>
                <span className="sr-only">{t('crud.actions')}</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {roomTypes.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={7} className="py-8 text-center text-muted">
                  {t('plans.families.noRoomTypes')}
                </TableCell>
              </TableRow>
            )}
            {roomTypes.map((roomType) => {
              const defaults = data.defaultsFor(roomType.id, plan.id)
              const name = pick(roomType.name, lang)
              const isDorm = roomType.kind === 'dorm'
              return (
                <TableRow key={roomType.id}>
                  <TableHead scope="row" className="h-auto py-2.5 font-normal">
                    <span className="flex items-center gap-2.5">
                      <span aria-hidden className="h-6 w-1 shrink-0 rounded-full" style={{ background: roomType.color }} />
                      <span className="grid">
                        <span className="text-[13px] font-semibold text-fg">{name}</span>
                        <span className="text-2xs font-semibold tracking-wide text-muted">
                          {roomType.code}
                          {isDorm && ` · ${t('plans.defaults.perBedShort')}`}
                        </span>
                      </span>
                    </span>
                  </TableHead>
                  {defaults ? (
                    <>
                      <TableCell className="text-right">
                        <MoneyText value={defaults.price} currency={currency} className="text-[14px] font-bold text-fg" />
                      </TableCell>
                      <TableCell className="text-muted">{summary(defaults.dow_adjustments)}</TableCell>
                      <TableCell className="text-right">
                        {isDorm ? <span className="text-subtle">—</span> : <MoneyText value={defaults.extra_adult_price} currency={currency} />}
                      </TableCell>
                      <TableCell className="text-right">
                        {isDorm ? (
                          <span className="text-subtle">—</span>
                        ) : (
                          <span className="whitespace-nowrap">
                            {`${formatMoney(defaults.extra_child_price, currency)} · ${t('plans.defaults.upToAge', { count: defaults.child_age_limit })}`}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {defaults.single_occupancy_price && !isDorm ? (
                          <MoneyText value={defaults.single_occupancy_price} currency={currency} />
                        ) : (
                          <span className="text-subtle">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {canManage && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('plans.defaults.editFor', { roomType: name })}
                            onClick={() => open({ roomType, plan, defaults })}
                          >
                            <Pencil aria-hidden />
                          </Button>
                        )}
                      </TableCell>
                    </>
                  ) : (
                    <>
                      <TableCell className="text-right">
                        <Badge tone="warning">{t('plans.families.noPrice')}</Badge>
                      </TableCell>
                      <TableCell colSpan={4} className="text-xs text-muted">
                        {t('plans.defaults.missingHint')}
                      </TableCell>
                      <TableCell className="text-right">
                        {canManage && (
                          <Button size="sm" aria-label={t('plans.defaults.setFor', { roomType: name })} onClick={() => open({ roomType, plan, defaults: null })}>
                            {t('plans.defaults.set')}
                          </Button>
                        )}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {dialog.target && (
        <DefaultsDialog
          key={dialog.key}
          open={dialog.open}
          onOpenChange={(next) => setDialog((current) => ({ ...current, open: next }))}
          target={dialog.target}
          currency={currency}
        />
      )}
    </div>
  )
}
