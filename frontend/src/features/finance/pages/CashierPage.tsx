import { useQuery } from '@tanstack/react-query'
import { Download, Lock, LockOpen, Wallet } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyInput, MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  closeShift,
  downloadShiftCsv,
  downloadShiftsCsv,
  financeKeys,
  getDaySummary,
  getShifts,
  openShift,
  useCurrentShift,
  useFinanceMutation,
  type CashShift,
  type CashShiftDetail,
  type CloseShiftInput,
} from '../api'
import { CashCount } from '../components/CashCount'
import { saveBlob } from '../download'
import { cashVerdict, countDenominations, moneyLabel, toNumber } from '../money'

/** `/app/cashier`: open the shift, see what came in, count the drawer and close it; history and exports. */
export default function CashierPage() {
  const { t } = useTranslation('finance')
  const { property } = useActiveProperty()
  const canCash = useCan('finance.cashier')
  const current = useCurrentShift()
  const currency = property?.currency ?? 'COP'
  const shift = current.data?.shift ?? null

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8">
      <PageHeader
        title={t('cashier.title')}
        description={t('cashier.description')}
        actions={canCash && property ? <ExportHistory businessDate={property.business_date} /> : null}
      />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid gap-6">
          {current.isPending ? (
            <LoadingState variant="rows" rows={4} />
          ) : current.isError ? (
            <ErrorState error={current.error} onRetry={() => current.refetch()} />
          ) : shift ? (
            <ShiftView shift={shift} currency={currency} canClose={canCash} />
          ) : canCash ? (
            <OpenShiftCard currency={currency} />
          ) : (
            <EmptyState icon={Wallet} title={t('cashier.noShift')} description={t('cashier.noPermission')} />
          )}
        </div>
        <DaySummary date={property?.business_date} currency={currency} />
      </div>
      {canCash && <ShiftHistory currency={currency} />}
    </div>
  )
}

function OpenShiftCard({ currency }: { currency: string }) {
  const { t } = useTranslation('finance')
  const ids = useId()
  const [opening, setOpening] = useState('')
  const [notes, setNotes] = useState('')
  const open = useFinanceMutation(() => openShift(opening || '0', notes.trim()), {
    onSuccess: () => toast.success(t('cashier.opened')),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    open.mutate(undefined)
  }

  return (
    <form onSubmit={submit} className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6" noValidate>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
          <LockOpen aria-hidden className="size-5" />
        </span>
        <div>
          <h2 className="text-lg font-bold">{t('cashier.openTitle')}</h2>
          <p className="text-sm text-muted">{t('cashier.openDescription')}</p>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-float`}>{t('cashier.openingFloat')}</Label>
          <MoneyInput id={`${ids}-float`} name="opening_float" value={opening} onChange={setOpening} currency={currency} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-notes`}>{t('cashier.notes')}</Label>
          <Textarea id={`${ids}-notes`} name="notes" rows={1} value={notes} onChange={(event) => setNotes(event.target.value)} className="min-h-9" />
        </div>
      </div>
      {open.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(open.error, t)}
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" loading={open.isPending}>
          {t('cashier.open')}
        </Button>
      </div>
    </form>
  )
}

function ShiftView({ shift, currency, canClose }: { shift: CashShiftDetail; currency: string; canClose: boolean }) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const [closing, setClosing] = useState(false)
  const { totals } = shift
  const others = totals.by_method.filter((row) => row.method !== 'cash')

  return (
    <section aria-labelledby={`${ids}-title`} className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-success" aria-hidden />
            <span id={`${ids}-title`} className="text-lg font-bold">
              {t('cashier.openShift')}
            </span>
          </p>
          <p className="text-sm text-muted">
            {t('cashier.openedBy', {
              name: shift.user.full_name || shift.user.email,
              time: formatDate(shift.opened_at, lang === 'es' ? "d MMM, HH:mm" : 'MMM d, h:mm a', lang),
            })}
          </p>
        </div>
        {canClose && (
          <Button variant="primary" onClick={() => setClosing(true)}>
            <Lock aria-hidden />
            {t('cashier.close')}
          </Button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)]">
        <div role="group" aria-labelledby={`${ids}-expected`} className="rounded-lg bg-surface-2 p-4">
          <p id={`${ids}-expected`} className="eyebrow">
            {t('cashier.expected')}
          </p>
          <p className="num mt-1 text-[30px] leading-9 font-semibold tracking-[-0.03em]">
            <MoneyText value={totals.expected_cash} currency={currency} />
          </p>
          <p className="mt-1 text-xs text-muted">{t('cashier.expectedHint')}</p>
        </div>
        <dl className="grid grid-cols-3 gap-3 self-center">
          {[
            [t('cashier.openingFloat'), totals.opening_float],
            [t('cashier.cashIn'), totals.cash_payments],
            [t('cashier.cashOut'), totals.cash_refunds],
          ].map(([label, value]) => (
            <div key={label} className="grid gap-0.5">
              <dt className="text-xs text-muted">{label}</dt>
              <dd className="text-sm font-semibold">
                <MoneyText value={value} currency={currency} />
              </dd>
            </div>
          ))}
        </dl>
      </div>

      {others.length > 0 && (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          <span className="font-semibold text-fg">{t('cashier.otherMethods')}</span>
          {others.map((row) => (
            <span key={row.method}>
              {t(`methods.${row.method}`)} · <MoneyText value={row.total} currency={currency} /> ({row.count})
            </span>
          ))}
        </p>
      )}

      <div className="grid gap-2">
        <h3 className="text-[15px] font-bold">{t('cashier.movements')}</h3>
        {shift.movements.length === 0 ? (
          <p className="py-3 text-sm text-muted">{t('cashier.noMovements')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-16">{t('cashier.time')}</TableHead>
                <TableHead>{t('cashier.reservation')}</TableHead>
                <TableHead className="hidden sm:table-cell">{t('folio.method')}</TableHead>
                <TableHead className="text-right">{t('folio.amount')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shift.movements.map((movement) => (
                <TableRow key={movement.id}>
                  <TableCell className="num text-xs text-muted">{formatDate(movement.created_at, 'HH:mm', lang)}</TableCell>
                  <TableCell>
                    {movement.reservation_id ? (
                      <Link to={`/app/reservations/${movement.reservation_id}`} className="num font-semibold text-fg hover:underline">
                        {movement.reservation_code}
                      </Link>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                    <span className="block text-xs text-muted">
                      {movement.guest_name}
                      <span className="sm:hidden"> · {t(`methods.${movement.method}`)}</span>
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {movement.kind === 'refund' ? `${t('folio.refund')} · ` : ''}
                    {t(`methods.${movement.method}`)}
                  </TableCell>
                  <TableCell className={cn('text-right font-semibold', movement.status !== 'approved' && 'text-subtle line-through')}>
                    <MoneyText value={movement.kind === 'refund' ? `-${movement.amount}` : movement.amount} currency={currency} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <CloseShiftDialog shift={shift} currency={currency} open={closing} onOpenChange={setClosing} />
    </section>
  )
}

function CloseShiftDialog({
  shift,
  currency,
  open,
  onOpenChange,
}: {
  shift: CashShiftDetail
  currency: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation('finance')
  const close = useFinanceMutation((input: CloseShiftInput) => closeShift(shift.id, input), {
    onSuccess: (closed) => {
      const difference = toNumber(closed.difference)
      if (difference === 0) toast.success(t('cashier.closedExact'))
      else toast.warning(t(difference > 0 ? 'cashier.closedOver' : 'cashier.closedShort', { amount: moneyLabel(Math.abs(difference), currency) }))
      onOpenChange(false)
    },
  })
  return (
    <Dialog open={open} onOpenChange={(next) => !close.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-2xl">
        <CloseShiftForm
          expected={shift.totals.expected_cash}
          currency={currency}
          pending={close.isPending}
          error={close.isError ? errorMessage(close.error, t) : null}
          onSubmit={(input) => close.mutate(input)}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function CloseShiftForm({
  expected,
  currency,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  expected: string
  currency: string
  pending: boolean
  error: string | null
  onSubmit: (input: CloseShiftInput) => void
  onCancel: () => void
}) {
  const { t } = useTranslation('finance')
  const ids = useId()
  const [mode, setMode] = useState<'count' | 'total'>('count')
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [total, setTotal] = useState('')
  const [notes, setNotes] = useState('')
  const counted = mode === 'count' ? countDenominations(counts) : toNumber(total)
  const hasCount = mode === 'count' ? Object.values(counts).some((count) => count > 0) : total !== ''
  const verdict = cashVerdict(counted, expected)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!hasCount) return
    const cleaned = Object.fromEntries(Object.entries(counts).filter(([, count]) => count > 0))
    onSubmit(mode === 'count' ? { denominations: cleaned, notes: notes.trim() } : { counted_cash: total, notes: notes.trim() })
  }

  const tone = verdict.kind === 'exact' ? 'success' : verdict.kind === 'over' ? 'info' : 'danger'
  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <DialogHeader>
        <DialogTitle>{t('cashier.close')}</DialogTitle>
        <DialogDescription>{t('cashier.closeDescription')}</DialogDescription>
      </DialogHeader>

      <ToggleGroup type="single" value={mode} onValueChange={(value) => value && setMode(value as 'count' | 'total')} aria-label={t('cashier.countMode')} className="w-fit">
        <ToggleGroupItem value="count">{t('cashier.byDenomination')}</ToggleGroupItem>
        <ToggleGroupItem value="total">{t('cashier.onlyTotal')}</ToggleGroupItem>
      </ToggleGroup>

      {mode === 'count' ? (
        <CashCount counts={counts} onChange={setCounts} currency={currency} />
      ) : (
        <div className="grid max-w-64 gap-1.5">
          <Label htmlFor={`${ids}-total`}>{t('cashier.countedTotal')}</Label>
          <MoneyInput id={`${ids}-total`} name="counted_cash" value={total} onChange={setTotal} currency={currency} />
        </div>
      )}

      <div className="grid gap-3 rounded-lg border border-border bg-surface-2 p-4 sm:grid-cols-[1fr_1fr_1.3fr] sm:items-center">
        <div>
          <p className="eyebrow">{t('cashier.counted')}</p>
          <p className="num text-lg font-semibold">
            <MoneyText value={counted} currency={currency} />
          </p>
        </div>
        <div>
          <p className="eyebrow">{t('cashier.expected')}</p>
          <p className="num text-lg font-semibold text-muted">
            <MoneyText value={expected} currency={currency} />
          </p>
        </div>
        <p
          role="status"
          aria-live="polite"
          className={cn(
            'rounded-md px-3 py-2 text-center text-sm font-bold',
            !hasCount && 'bg-surface text-muted',
            hasCount && tone === 'success' && 'bg-success-soft text-success-ink',
            hasCount && tone === 'info' && 'bg-info-soft text-info-ink',
            hasCount && tone === 'danger' && 'bg-danger-soft text-danger-ink',
          )}
        >
          {!hasCount
            ? t('cashier.verdictEmpty')
            : verdict.kind === 'exact'
              ? t('cashier.verdictExact')
              : t(verdict.kind === 'over' ? 'cashier.verdictOver' : 'cashier.verdictShort', { amount: moneyLabel(verdict.amount, currency) })}
        </p>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-notes`}>{t('cashier.closeNotes')}</Label>
        <Textarea id={`${ids}-notes`} name="close_notes" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {error}
        </p>
      )}

      <DialogFooter>
        <Button variant="secondary" onClick={onCancel} disabled={pending}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={pending} disabled={!hasCount}>
          {t('cashier.close')}
        </Button>
      </DialogFooter>
    </form>
  )
}

function DaySummary({ date, currency }: { date: string | undefined; currency: string }) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const summary = useQuery({ queryKey: financeKeys.summary(date), queryFn: () => getDaySummary(date), enabled: Boolean(date) })
  const data = summary.data
  return (
    <section aria-labelledby={`${ids}-title`} className="grid gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs">
      <div>
        <h2 id={`${ids}-title`} className="text-[15px] font-bold">
          {t('cashier.day', { date: formatDate(date, 'd MMM', lang) })}
        </h2>
        <p className="text-xs text-muted">{t('cashier.dayHint')}</p>
      </div>
      {summary.isPending ? (
        <LoadingState variant="rows" rows={3} className="p-0" />
      ) : summary.isError || !data ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} className="py-4" />
      ) : (
        <>
          <p className="num text-2xl font-semibold tracking-[-0.02em]">
            <MoneyText value={data.net_total} currency={currency} />
          </p>
          {data.by_method.length === 0 ? (
            <p className="text-sm text-muted">{t('cashier.dayEmpty')}</p>
          ) : (
            <ul className="grid gap-2 text-sm">
              {data.by_method.map((row) => (
                <li key={row.method} className="flex items-baseline justify-between gap-3">
                  <span>{t(`methods.${row.method}`)}</span>
                  <span className="flex-1 border-b border-dotted border-border-strong" aria-hidden />
                  <span className="text-xs text-muted">×{row.count}</span>
                  <MoneyText value={row.total} currency={currency} className="font-semibold" />
                </li>
              ))}
              {toNumber(data.refunds.total) > 0 && (
                <li className="flex items-baseline justify-between gap-3 text-muted">
                  <span>{t('folio.refunded')}</span>
                  <span className="flex-1 border-b border-dotted border-border" aria-hidden />
                  <MoneyText value={`-${data.refunds.total}`} currency={currency} />
                </li>
              )}
            </ul>
          )}
          <p className="border-t border-border pt-3 text-xs text-muted">
            {t('cashier.dayCharges', { total: moneyLabel(data.charges.total, currency) })}
          </p>
        </>
      )}
    </section>
  )
}

function ShiftHistory({ currency }: { currency: string }) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const [page, setPage] = useState(1)
  const shifts = useQuery({ queryKey: financeKeys.shifts(page), queryFn: () => getShifts(page) })
  const rows = shifts.data?.results ?? []
  const pages = Math.max(1, Math.ceil((shifts.data?.count ?? 0) / 10))

  async function download(shift: CashShift) {
    try {
      saveBlob(await downloadShiftCsv(shift.id), `caja-${shift.opened_at.slice(0, 10)}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <section aria-labelledby={`${ids}-title`} className="grid gap-3">
      <h2 id={`${ids}-title`} className="text-lg font-bold">
        {t('cashier.history')}
      </h2>
      {shifts.isPending ? (
        <LoadingState variant="rows" rows={3} />
      ) : shifts.isError ? (
        <ErrorState error={shifts.error} onRetry={() => shifts.refetch()} className="rounded-xl border border-border bg-surface py-8" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t('cashier.historyEmpty')}</p>
      ) : (
        <div className="rounded-xl border border-border bg-surface shadow-xs">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t('cashier.shift')}</TableHead>
                <TableHead className="hidden text-right sm:table-cell">{t('cashier.openingFloat')}</TableHead>
                <TableHead className="hidden text-right md:table-cell">{t('cashier.expected')}</TableHead>
                <TableHead className="hidden text-right md:table-cell">{t('cashier.counted')}</TableHead>
                <TableHead className="text-right">{t('cashier.difference')}</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">{t('folio.actions')}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((shift) => {
                const difference = shift.difference === null ? null : toNumber(shift.difference)
                return (
                  <TableRow key={shift.id}>
                    <TableCell>
                      <span className="font-medium text-fg">{shift.user.full_name || shift.user.email}</span>
                      <span className="num block text-xs text-muted">
                        {formatDate(shift.opened_at, lang === 'es' ? "d MMM, HH:mm" : 'MMM d, h:mm a', lang)}
                        {shift.closed_at ? ` – ${formatDate(shift.closed_at, 'HH:mm', lang)}` : ''}
                      </span>
                    </TableCell>
                    <TableCell className="hidden text-right sm:table-cell">
                      <MoneyText value={shift.opening_float} currency={currency} />
                    </TableCell>
                    <TableCell className="hidden text-right md:table-cell">
                      {shift.expected_cash === null ? '—' : <MoneyText value={shift.expected_cash} currency={currency} />}
                    </TableCell>
                    <TableCell className="hidden text-right md:table-cell">
                      {shift.counted_cash === null ? '—' : <MoneyText value={shift.counted_cash} currency={currency} />}
                    </TableCell>
                    <TableCell className="text-right">
                      {difference === null ? (
                        <Badge tone="success">{t('cashier.stillOpen')}</Badge>
                      ) : difference === 0 ? (
                        <Badge tone="success">{t('cashier.verdictExact')}</Badge>
                      ) : (
                        <MoneyText value={shift.difference} currency={currency} highlightNegative className="font-semibold" />
                      )}
                    </TableCell>
                    <TableCell className="px-1 text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('cashier.downloadShift', { date: formatDate(shift.opened_at, 'd MMM', lang) })}
                        onClick={() => void download(shift)}
                      >
                        <Download aria-hidden />
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          {pages > 1 && (
            <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-2 text-sm">
              <span className="text-muted">{t('common:table.pageOf', { page, pages })}</span>
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                {t('common:table.previous')}
              </Button>
              <Button size="sm" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>
                {t('common:table.next')}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function ExportHistory({ businessDate }: { businessDate: string }) {
  const { t } = useTranslation('finance')
  const [busy, setBusy] = useState(false)

  async function exportCsv() {
    const end = parseDate(businessDate) ?? new Date()
    const start = new Date(end)
    start.setDate(start.getDate() - 30)
    setBusy(true)
    try {
      saveBlob(await downloadShiftsCsv(toISODate(start), toISODate(end)), `turnos-caja-${toISODate(end)}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button onClick={() => void exportCsv()} loading={busy}>
      <Download aria-hidden />
      {t('cashier.exportHistory')}
    </Button>
  )
}
