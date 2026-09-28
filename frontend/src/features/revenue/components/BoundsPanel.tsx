import { Eraser, Save } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { errorMessage } from '@/lib/errors'
import { formatMoney, formatNumber, normalizeLang, type Lang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useBounds, useDeleteBounds, useRevenueOptions, useSaveBounds, type PriceBounds, type RatePlanRef, type RoomTypeRef } from '../api'
import { pick } from '../lib/format'

interface Line {
  plan: RatePlanRef
  roomType: RoomTypeRef
  defaultPrice: string | null
  bounds: PriceBounds | undefined
}

/** Floor and ceiling per category of each active base plan: no recommendation ever leaves them. */
export function BoundsPanel() {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('revenue.manage')
  const options = useRevenueOptions()
  const bounds = useBounds()

  if (options.isPending || bounds.isPending) return <LoadingState variant="rows" rows={4} />
  if (options.isError || bounds.isError) {
    return (
      <ErrorState
        error={options.error ?? bounds.error}
        onRetry={() => {
          void options.refetch()
          void bounds.refetch()
        }}
      />
    )
  }
  const roomTypes = new Map(options.data.room_types.map((roomType) => [roomType.id, roomType]))
  const lines: Line[] = options.data.rate_plans.flatMap((plan) =>
    plan.room_types.flatMap((id) => {
      const roomType = roomTypes.get(id)
      if (!roomType) return []
      return [
        {
          plan,
          roomType,
          defaultPrice: plan.default_prices[id] ?? null,
          bounds: bounds.data.find((item) => item.room_type === id && item.rate_plan === plan.id),
        },
      ]
    }),
  )
  const currency = options.data.currency

  return (
    <div className="grid gap-4">
      <p className="max-w-2xl text-sm text-muted">{t('bounds.intro')}</p>
      {lines.length === 0 ? (
        <p className="rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-muted">{t('bounds.empty')}</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
          <Table aria-label={t('bounds.table')}>
            <TableHeader>
              <TableRow>
                <TableHead>{t('bounds.category')}</TableHead>
                <TableHead>{t('bounds.plan')}</TableHead>
                <TableHead className="text-right">{t('bounds.default')}</TableHead>
                <TableHead>{t('bounds.min')}</TableHead>
                <TableHead>{t('bounds.max')}</TableHead>
                {canManage && (
                  <TableHead>
                    <span className="sr-only">{t('bounds.actions')}</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => (
                <BoundsRow
                  key={`${line.plan.id}:${line.roomType.id}:${line.bounds?.id ?? 'none'}:${line.bounds?.updated_at ?? ''}`}
                  line={line}
                  currency={currency}
                  lang={lang}
                  canManage={canManage}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function ratio(value: string, reference: string | null, lang: Lang): string | null {
  const amount = Number(value)
  const base = Number(reference)
  if (!value || !reference || !Number.isFinite(amount) || !base) return null
  return `${formatNumber(Math.round((amount / base) * 100), lang)} %`
}

function BoundsRow({ line, currency, lang, canManage }: { line: Line; currency: string; lang: Lang; canManage: boolean }) {
  const { t } = useTranslation('revenue')
  const [min, setMin] = useState(line.bounds?.min_price ? String(Number(line.bounds.min_price)) : '')
  const [max, setMax] = useState(line.bounds?.max_price ? String(Number(line.bounds.max_price)) : '')
  const [error, setError] = useState<string | null>(null)
  const save = useSaveBounds()
  const remove = useDeleteBounds()
  const names = { roomType: pick(line.roomType.name, lang), plan: pick(line.plan.name, lang) }
  const minRatio = ratio(min, line.defaultPrice, lang)
  const maxRatio = ratio(max, line.defaultPrice, lang)

  function submit() {
    if (!min && !max) return setError(t('bounds.needOne'))
    if (min && max && Number(max) < Number(min)) return setError(t('bounds.order'))
    setError(null)
    save.mutate(
      { room_type: line.roomType.id, rate_plan: line.plan.id, min_price: min || null, max_price: max || null },
      {
        onSuccess: () => toast.success(t('bounds.saved')),
        onError: (failure) => setError(errorMessage(failure, t)),
      },
    )
  }

  function clear() {
    if (!line.bounds) return
    remove.mutate(line.bounds.id, {
      onSuccess: () => toast.success(t('bounds.cleared')),
      onError: (failure) => setError(errorMessage(failure, t)),
    })
  }

  return (
    <TableRow>
      <TableCell>
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-4 w-1 rounded-full" style={{ background: line.roomType.color }} />
          <span className="font-semibold text-fg">{names.roomType}</span>
          <span className="text-2xs font-semibold text-muted">{line.roomType.code}</span>
        </span>
        {error && (
          <p role="alert" className="mt-1 text-xs font-medium text-danger-ink">
            {error}
          </p>
        )}
      </TableCell>
      <TableCell className="text-muted">{line.plan.code}</TableCell>
      <TableCell className="num text-right text-muted">
        {line.defaultPrice ? formatMoney(line.defaultPrice, currency) : <span className="text-xs">{t('bounds.noDefault')}</span>}
      </TableCell>
      <TableCell className="min-w-40">
        <MoneyInput value={min} onChange={setMin} currency={currency} disabled={!canManage} aria-label={t('bounds.minLabel', names)} />
        {minRatio && <p className="mt-1 text-2xs text-muted">{t('bounds.ofDefault', { value: minRatio })}</p>}
      </TableCell>
      <TableCell className="min-w-40">
        <MoneyInput value={max} onChange={setMax} currency={currency} disabled={!canManage} aria-label={t('bounds.maxLabel', names)} />
        {maxRatio && <p className="mt-1 text-2xs text-muted">{t('bounds.ofDefault', { value: maxRatio })}</p>}
      </TableCell>
      {canManage && (
        <TableCell>
          <span className="flex justify-end gap-1">
            <Button size="sm" onClick={submit} loading={save.isPending} aria-label={t('bounds.saveRow', names)}>
              <Save aria-hidden />
              <span className="hidden sm:inline">{t('bounds.save')}</span>
            </Button>
            {line.bounds && (
              <Button variant="ghost" size="icon-sm" onClick={clear} loading={remove.isPending} aria-label={t('bounds.clear', names)}>
                <Eraser aria-hidden />
              </Button>
            )}
          </span>
        </TableCell>
      )}
    </TableRow>
  )
}
