import { useMutation } from '@tanstack/react-query'
import {
  ArrowRightLeft,
  Building2,
  ChevronDown,
  Copy,
  ExternalLink,
  Link2,
  MoreHorizontal,
  Plus,
  ReceiptText,
  RefreshCw,
  Split,
  Undo2,
  UserRound,
  Wallet,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatRelative, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  ensureFolio,
  syncIntent,
  transferCharge,
  transferPayment,
  useFinanceMutation,
  useFolio,
  useReservationFolios,
  type Charge,
  type FolioDetail,
  type FolioSummary,
  type Payment,
  type PaymentIntent,
  type Refund,
} from '../api'
import { balanceState, fromCents, moneyLabel, toCents } from '../money'
import { AddChargeDialog } from './AddChargeDialog'
import { PaymentLinkDialog } from './PaymentLinkDialog'
import { LinkStatusBadge, PaymentStatusBadge } from './PaymentStatusBadge'
import { RecordPaymentDialog } from './RecordPaymentDialog'
import { CompleteRefundDialog, RefundDialog, VoidChargeDialog, VoidPaymentDialog } from './RiskDialogs'
import { SplitChargeDialog } from './SplitChargeDialog'

export interface FolioPanelProps {
  /** Reservation whose folio(s) to show; the guest folio is created when missing (needs finance.collect). */
  reservationId: string
  /** Dense layout for check-in / check-out dialogs: balance and actions, lines behind "Ver detalle". */
  compact?: boolean
  /** Called after every successful change (charge, payment, void, refund, payment link). */
  onChange?: () => void
  className?: string
}

type OpenDialog =
  | { type: 'payment' }
  | { type: 'charge' }
  | { type: 'link' }
  | { type: 'voidCharge'; charge: Charge }
  | { type: 'voidPayment'; payment: Payment }
  | { type: 'refund'; payment: Payment }
  | { type: 'completeRefund'; refund: Refund }
  | { type: 'split'; charge: Charge }

/** P4: how a folio is called in its tab and in "Move to…" menus. */
function useFolioName() {
  const { t } = useTranslation('finance')
  return (folio: FolioSummary, index = 0) => {
    if (folio.folio_type === 'company' && folio.company) return folio.company.trade_name || folio.company.legal_name
    if (folio.folio_type === 'guest' && folio.guest) return t('folio.guestTab', { name: folio.guest.full_name.split(' ')[0] })
    if (folio.label) return folio.label
    return index === 0 ? t('folio.main') : t('folio.numbered', { number: index + 1 })
  }
}

/**
 * The reservation's bill: what the guest owes, how much of the stay is paid, every charge and payment,
 * and the money actions allowed to the signed-in role (finance.collect / void / refund).
 * Exported for C1 (reservation detail, check-in/out) and C5: `<FolioPanel reservationId={id} />`.
 */
export function FolioPanel({ reservationId, compact = false, onChange, className }: FolioPanelProps) {
  const { t } = useTranslation('finance')
  const canCollect = useCan('finance.collect')
  const folios = useReservationFolios(reservationId)
  const list = folios.data?.results
  const [chosen, setChosen] = useState<string | null>(null)
  const folioId = pickFolio(list, chosen)
  const folio = useFolio(folioId)
  const create = useMutation({ mutationFn: () => ensureFolio(reservationId), onSuccess: () => folios.refetch() })
  const needsFolio = list !== undefined && list.length === 0
  const { mutate: createFolio, isIdle: createIdle } = create

  useEffect(() => {
    if (needsFolio && canCollect && createIdle) createFolio()
  }, [needsFolio, canCollect, createIdle, createFolio])

  if (folios.isError) return <ErrorState error={folios.error} onRetry={() => folios.refetch()} className={className} />
  if (needsFolio && !canCollect)
    return <EmptyState icon={ReceiptText} title={t('folio.none')} description={t('folio.noneHint')} className={className} />
  if (create.isError) return <ErrorState error={create.error} onRetry={() => create.reset()} className={className} />
  if (folio.isError) return <ErrorState error={folio.error} onRetry={() => folio.refetch()} className={className} />
  if (!folio.data) return <LoadingState variant="rows" rows={compact ? 3 : 6} className={className} />

  return (
    <FolioView
      folio={folio.data}
      folios={list ?? []}
      onPickFolio={setChosen}
      compact={compact}
      onChange={onChange}
      className={className}
    />
  )
}

function pickFolio(list: FolioSummary[] | undefined, chosen: string | null): string | null {
  if (!list?.length) return null
  if (chosen && list.some((folio) => folio.id === chosen)) return chosen
  return (list.find((folio) => folio.folio_type === 'guest') ?? list[0])!.id
}

function FolioView({
  folio,
  folios,
  onPickFolio,
  compact,
  onChange,
  className,
}: {
  folio: FolioDetail
  folios: FolioSummary[]
  onPickFolio: (id: string) => void
  compact: boolean
  onChange?: () => void
  className?: string
}) {
  const { t } = useTranslation('finance')
  const canCollect = useCan('finance.collect')
  const canVoid = useCan('finance.void')
  const canRefund = useCan('finance.refund')
  const folioName = useFolioName()
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const [expanded, setExpanded] = useState(!compact)
  const currency = folio.currency
  const open = folio.status === 'open'
  const isCompany = folio.folio_type === 'company'
  const split = folios.length > 1

  // What this folio owes: its part of the reservation (the nights not posted yet included) — the whole reservation
  // when it is the only folio — or, for folios without reservation, the folio itself.
  const due = folio.totals.expected_balance ?? folio.totals.reservation_balance ?? folio.totals.balance
  // Before the guest leaves: the guest's part plus the part of companies without credit (P4).
  const checkoutDue = folio.totals.reservation_balance
  const paidCents = toCents(folio.totals.payments_total) - toCents(folio.totals.refunds_total)
  const totalCents = toCents(due) + paidCents
  const state = balanceState(due)
  const close = () => setDialog(null)
  const done = () => onChange?.()
  // Where a charge or a payment of this folio can move: the other open folios of the reservation.
  const targets = open && canCollect ? folios.filter((item) => item.id !== folio.id && item.status === 'open') : []
  const moveCharge = useFinanceMutation(({ charge, to }: { charge: Charge; to: FolioSummary }) => transferCharge(charge.id, to.id), {
    onSuccess: (_, { charge, to }) => {
      toast.success(t('move.chargeMoved', { description: charge.description, folio: folioName(to) }))
      done()
    },
  })
  const movePayment = useFinanceMutation(({ payment, to }: { payment: Payment; to: FolioSummary }) => transferPayment(payment.id, to.id), {
    onSuccess: (_, { to }) => {
      toast.success(t('move.paymentMoved', { folio: folioName(to) }))
      done()
    },
  })
  const moveError = moveCharge.error ?? movePayment.error

  let hint: string
  if (state === 'credit') hint = t('folio.creditHint')
  else if (isCompany) hint = folio.company?.credit_enabled ? t('folio.companyCreditHint') : t('folio.companyNoCreditHint')
  else if (split && folio.folio_type === 'guest') hint = t('folio.guestPartHint')
  else hint = folio.totals.reservation_balance != null ? t('folio.includesStay') : t('folio.houseHint')

  return (
    <section
      aria-label={t('folio.region', { code: folio.reservation?.code ?? '' })}
      className={cn('@container overflow-hidden rounded-xl border border-border bg-surface shadow-xs', className)}
    >
      {split && (
        <div role="tablist" aria-label={t('folio.pick')} className="flex gap-1 overflow-x-auto border-b border-border px-3 pt-2 [scrollbar-width:none]">
          {folios.map((item, index) => {
            const active = item.id === folio.id
            const Icon = item.folio_type === 'company' ? Building2 : item.folio_type === 'guest' ? UserRound : ReceiptText
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onPickFolio(item.id)}
                className={cn(
                  '-mb-px grid min-w-0 shrink-0 gap-0.5 rounded-t-lg border border-b-0 px-3 pt-2 pb-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                  active ? 'border-border bg-surface text-fg' : 'border-transparent text-muted hover:bg-surface-2 hover:text-fg',
                )}
              >
                <span className="flex max-w-56 items-center gap-1.5 text-[13px] font-semibold">
                  <Icon aria-hidden className={cn('size-3.5 shrink-0', active && item.folio_type === 'company' && 'text-accent-ink')} />
                  <span className="truncate">{folioName(item, index)}</span>
                  {item.status === 'closed' && <span className="text-xs font-normal text-subtle">· {t('folio.closedShort')}</span>}
                </span>
                <MoneyText value={item.totals.expected_balance ?? item.totals.balance} currency={item.currency} className="text-xs text-muted" />
              </button>
            )
          })}
        </div>
      )}

      <BillStub
        state={state}
        due={due}
        paid={fromCents(paidCents)}
        total={fromCents(totalCents)}
        currency={currency}
        folio={folio}
        hint={hint}
        totalLabel={split ? t('folio.folioTotal') : undefined}
        eyebrow={isCompany ? t(`folio.companyState.${state}`) : undefined}
        note={
          split && checkoutDue != null && toCents(checkoutDue) !== toCents(due) ? (
            <p className="mt-1 text-[13px] text-muted">
              {t('folio.checkoutDue', { amount: moneyLabel(checkoutDue, currency) })}
            </p>
          ) : null
        }
        actions={
          open && canCollect ? (
            <div className="grid w-full grid-cols-2 gap-2 @xl:flex @xl:w-auto @xl:flex-wrap @xl:items-center">
              {!isCompany && (
                <Button variant="secondary" className="w-full @xl:w-auto" onClick={() => setDialog({ type: 'link' })}>
                  <Link2 aria-hidden />
                  {t('actions.paymentLink')}
                </Button>
              )}
              <Button variant="secondary" className={cn('w-full @xl:w-auto', isCompany && 'col-span-2')} onClick={() => setDialog({ type: 'charge' })}>
                <Plus aria-hidden />
                {t('actions.addCharge')}
              </Button>
              <Button
                variant="primary"
                className="order-first col-span-2 w-full @xl:order-none @xl:w-auto"
                onClick={() => setDialog({ type: 'payment' })}
              >
                <Wallet aria-hidden />
                {t('actions.recordPayment')}
              </Button>
            </div>
          ) : !open ? (
            <Badge tone="stone">{t('folio.closed')}</Badge>
          ) : null
        }
      />

      <TearLine />

      {compact && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="flex w-full items-center justify-between px-5 pt-1 pb-4 text-sm font-semibold text-muted hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
        >
          {t('folio.details', { count: folio.charges.length + folio.payments.length })}
          <ChevronDown aria-hidden className={cn('size-4 transition-transform', expanded && 'rotate-180')} />
        </button>
      )}

      {expanded && (
        <div className="grid gap-7 px-5 pt-1 pb-6">
          {moveError && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {errorMessage(moveError, t)}
            </p>
          )}
          <ChargesTable
            charges={folio.charges}
            currency={currency}
            onVoid={open && canVoid ? (charge) => setDialog({ type: 'voidCharge', charge }) : undefined}
            onSplit={open && canCollect ? (charge) => setDialog({ type: 'split', charge }) : undefined}
            moveTargets={targets.map((target) => ({ folio: target, name: folioName(target) }))}
            onMove={(charge, to) => moveCharge.mutate({ charge, to })}
          />
          <PaymentsTable
            payments={folio.payments}
            refunds={folio.refunds}
            currency={currency}
            onRefund={open && canRefund ? (payment) => setDialog({ type: 'refund', payment }) : undefined}
            onVoid={open && canVoid ? (payment) => setDialog({ type: 'voidPayment', payment }) : undefined}
            onComplete={canRefund ? (refund) => setDialog({ type: 'completeRefund', refund }) : undefined}
            moveTargets={targets.map((target) => ({ folio: target, name: folioName(target) }))}
            onMove={(payment, to) => movePayment.mutate({ payment, to })}
          />
          {folio.intents.length > 0 && <LinksList intents={folio.intents} currency={currency} canSync={canCollect} onChange={done} />}
        </div>
      )}

      <RecordPaymentDialog
        open={dialog?.type === 'payment'}
        onOpenChange={(value) => !value && close()}
        folioId={folio.id}
        suggestedAmount={state === 'due' ? due : '0'}
        currency={currency}
        onDone={done}
      />
      <AddChargeDialog
        open={dialog?.type === 'charge'}
        onOpenChange={(value) => !value && close()}
        folioId={folio.id}
        currency={currency}
        onDone={done}
      />
      <PaymentLinkDialog
        open={dialog?.type === 'link'}
        onOpenChange={(value) => !value && close()}
        folioId={folio.id}
        suggestedAmount={state === 'due' ? due : '0'}
        currency={currency}
        guest={folio.guest}
        onDone={done}
      />
      {dialog?.type === 'voidCharge' && (
        <VoidChargeDialog charge={dialog.charge} currency={currency} onOpenChange={(value) => !value && close()} onDone={done} />
      )}
      {dialog?.type === 'voidPayment' && (
        <VoidPaymentDialog payment={dialog.payment} currency={currency} onOpenChange={(value) => !value && close()} onDone={done} />
      )}
      {dialog?.type === 'refund' && (
        <RefundDialog payment={dialog.payment} currency={currency} onOpenChange={(value) => !value && close()} onDone={done} />
      )}
      {dialog?.type === 'completeRefund' && (
        <CompleteRefundDialog refund={dialog.refund} currency={currency} onOpenChange={(value) => !value && close()} onDone={done} />
      )}
      {dialog?.type === 'split' && (
        <SplitChargeDialog
          charge={dialog.charge}
          currency={currency}
          currentFolio={{ folio, name: folioName(folio) }}
          targets={targets.map((target) => ({ folio: target, name: folioName(target) }))}
          onOpenChange={(value) => !value && close()}
          onDone={done}
        />
      )}
    </section>
  )
}

const STATE_TONE = {
  due: 'text-fg',
  settled: 'text-success-ink',
  credit: 'text-info-ink',
} as const

/** Top of the bill: the balance, a paid-vs-total meter and the stay figures. */
function BillStub({
  state,
  due,
  paid,
  total,
  currency,
  folio,
  actions,
  hint,
  eyebrow,
  note,
  totalLabel,
}: {
  state: 'due' | 'settled' | 'credit'
  due: string
  paid: string
  total: string
  currency: string
  folio: FolioDetail
  actions: ReactNode
  /** One sentence under the amount: what the number includes. */
  hint: string
  /** Replaces the state label (company folios speak of the company, not the guest). */
  eyebrow?: string
  note?: ReactNode
  /** Label of the first figure ("Total de la estadía"; "Total de este folio" when the bill is split). */
  totalLabel?: string
}) {
  const { t } = useTranslation('finance')
  const totalCents = toCents(total)
  const ratio = totalCents > 0 ? Math.min(1, Math.max(0, toCents(paid) / totalCents)) : 0
  const shown = state === 'credit' ? fromCents(-toCents(due)) : due
  const figures = [
    { label: totalLabel ?? t('folio.stayTotal'), value: total },
    { label: t('folio.charged'), value: folio.totals.charges_total },
    { label: t('folio.paid'), value: folio.totals.payments_total },
    { label: t('folio.refunded'), value: folio.totals.refunds_total },
  ]
  return (
    <div className="grid gap-5 px-5 pt-5 pb-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow">{eyebrow ?? t(`folio.state.${state}`)}</p>
          <p className={cn('num mt-1 text-[34px] leading-10 font-semibold tracking-[-0.035em]', STATE_TONE[state])}>
            <MoneyText value={shown} currency={currency} />
          </p>
          <p className="mt-1 max-w-md text-[13px] text-muted">{hint}</p>
          {note}
        </div>
        {actions && <div className="flex w-full flex-wrap items-center gap-2 @xl:w-auto">{actions}</div>}
      </div>

      {totalCents > 0 && (
        <div className="grid gap-1.5">
          <div
            role="meter"
            aria-label={t('folio.paidMeter')}
            aria-valuemin={0}
            aria-valuemax={totalCents / 100}
            aria-valuenow={toCents(paid) / 100}
            aria-valuetext={t('folio.paidOf', { paid: moneyLabel(paid, currency), total: moneyLabel(total, currency) })}
            className="h-1.5 overflow-hidden rounded-full bg-surface-3"
          >
            <div
              className={cn('h-full rounded-full transition-[width] duration-500', state === 'due' ? 'bg-accent' : 'bg-success')}
              style={{ width: `${ratio * 100}%` }}
            />
          </div>
          <p className="text-xs text-muted">{t('folio.paidOf', { paid: moneyLabel(paid, currency), total: moneyLabel(total, currency) })}</p>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 @lg:grid-cols-4">
        {figures.map(({ label, value }) => (
          <div key={label} className="grid gap-0.5">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="text-sm font-semibold">
              <MoneyText value={value} currency={currency} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** Perforated edge between the stub and the lines, with punched notches — the folio reads as a hotel bill. */
function TearLine() {
  return (
    <div aria-hidden className="relative h-6">
      <span className="absolute top-1/2 -left-3 size-6 -translate-y-1/2 rounded-full border border-border bg-bg" />
      <span className="absolute inset-x-5 top-1/2 border-t-[1.5px] border-dashed border-border-strong" />
      <span className="absolute top-1/2 -right-3 size-6 -translate-y-1/2 rounded-full border border-border bg-bg" />
    </div>
  )
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <h3 className="flex items-baseline gap-2 text-[15px] font-bold">
      {title}
      <span className="num text-xs font-semibold text-subtle">{count}</span>
    </h3>
  )
}

function RowMenu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">{children}</DropdownMenuContent>
    </DropdownMenu>
  )
}

interface MoveTarget {
  folio: FolioSummary
  name: string
}

function ChargesTable({
  charges,
  currency,
  onVoid,
  onSplit,
  moveTargets = [],
  onMove,
}: {
  charges: Charge[]
  currency: string
  onVoid?: (charge: Charge) => void
  onSplit?: (charge: Charge) => void
  moveTargets?: MoveTarget[]
  onMove?: (charge: Charge, to: FolioSummary) => void
}) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const hasActions = Boolean(onVoid || onSplit || (onMove && moveTargets.length))
  return (
    <div className="grid gap-2">
      <SectionTitle title={t('folio.charges')} count={charges.filter((charge) => !charge.voided).length} />
      {charges.length === 0 ? (
        <p className="py-3 text-sm text-muted">{t('folio.noCharges')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="hidden w-20 @sm:table-cell">{t('folio.date')}</TableHead>
              <TableHead>{t('folio.concept')}</TableHead>
              <TableHead className="hidden text-right @xl:table-cell">{t('folio.net')}</TableHead>
              <TableHead className="hidden text-right @xl:table-cell">{t('folio.tax')}</TableHead>
              <TableHead className="text-right">{t('folio.total')}</TableHead>
              {hasActions && <TableHead className="w-10"><span className="sr-only">{t('folio.actions')}</span></TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {charges.map((charge) => (
              <TableRow key={charge.id} className={cn(charge.voided && 'text-subtle')}>
                <TableCell className="num hidden text-xs text-muted @sm:table-cell">{formatDate(charge.business_date, 'd MMM', lang)}</TableCell>
                <TableCell>
                  <span className={cn('font-medium', charge.voided ? 'text-subtle line-through' : 'text-fg')}>{charge.description}</span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted">
                    {charge.quantity > 1 && (
                      <span className="num">
                        {charge.quantity} × {moneyLabel(charge.unit_price, currency)}
                      </span>
                    )}
                    <span>{t(`kinds.${charge.kind}`)}</span>
                    {charge.tax_exempt && <Badge tone="info">{t('charge.exempt')}</Badge>}
                    {charge.voided && (
                      <>
                        <Badge tone="stone">{t('folio.voided')}</Badge>
                        {charge.void_reason && <span className="italic">{charge.void_reason}</span>}
                      </>
                    )}
                  </span>
                </TableCell>
                <TableCell className="hidden text-right @xl:table-cell">
                  <MoneyText value={charge.amount} currency={currency} className={cn(charge.voided && 'line-through')} />
                </TableCell>
                <TableCell className="hidden text-right text-muted @xl:table-cell">
                  {charge.tax_exempt ? '—' : <MoneyText value={charge.tax_amount} currency={currency} className={cn(charge.voided && 'line-through')} />}
                </TableCell>
                <TableCell className="text-right font-semibold">
                  <MoneyText value={charge.total} currency={currency} className={cn(charge.voided && 'line-through')} />
                </TableCell>
                {hasActions && (
                  <TableCell className="px-1 text-right">
                    {!charge.voided && (
                      <RowMenu label={t('folio.chargeActions', { description: charge.description })}>
                        {onMove && moveTargets.length > 0 && (
                          <>
                            <DropdownMenuLabel className="text-xs font-semibold text-muted">{t('move.chargeTo')}</DropdownMenuLabel>
                            {moveTargets.map((target) => (
                              <DropdownMenuItem key={target.folio.id} onSelect={() => onMove(charge, target.folio)}>
                                <ArrowRightLeft aria-hidden />
                                {target.name}
                              </DropdownMenuItem>
                            ))}
                          </>
                        )}
                        {onSplit && toCents(charge.total) > 0 && (
                          <DropdownMenuItem onSelect={() => onSplit(charge)}>
                            <Split aria-hidden />
                            {t('split.action')}
                          </DropdownMenuItem>
                        )}
                        {onVoid && (
                          <>
                            {(onSplit || (onMove && moveTargets.length > 0)) && <DropdownMenuSeparator />}
                            <DropdownMenuItem destructive onSelect={() => onVoid(charge)}>
                              <Undo2 aria-hidden />
                              {t('risk.voidChargeTitle')}
                            </DropdownMenuItem>
                          </>
                        )}
                      </RowMenu>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

function PaymentsTable({
  payments,
  refunds,
  currency,
  onRefund,
  onVoid,
  onComplete,
  moveTargets = [],
  onMove,
}: {
  payments: Payment[]
  refunds: Refund[]
  currency: string
  onRefund?: (payment: Payment) => void
  onVoid?: (payment: Payment) => void
  onComplete?: (refund: Refund) => void
  moveTargets?: MoveTarget[]
  onMove?: (payment: Payment, to: FolioSummary) => void
}) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const canMove = Boolean(onMove && moveTargets.length)
  const hasActions = Boolean(onRefund || onVoid || onComplete || canMove)
  const refundsOf = (payment: Payment) => refunds.filter((refund) => refund.payment_id === payment.id)
  return (
    <div className="grid gap-2">
      <SectionTitle title={t('folio.payments')} count={payments.filter((payment) => payment.status === 'approved').length} />
      {payments.length === 0 ? (
        <p className="py-3 text-sm text-muted">{t('folio.noPayments')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="hidden w-20 @sm:table-cell">{t('folio.date')}</TableHead>
              <TableHead>{t('folio.method')}</TableHead>
              <TableHead className="hidden @md:table-cell">{t('folio.status')}</TableHead>
              <TableHead className="text-right">{t('folio.amount')}</TableHead>
              {hasActions && <TableHead className="w-10"><span className="sr-only">{t('folio.actions')}</span></TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {payments.map((payment) => {
              const canRefund = onRefund && payment.status === 'approved' && toCents(payment.refundable_amount) > 0
              const canVoid = onVoid && payment.can_void
              // only approved payments without refunds can move (the server checks it too)
              const movable = canMove && payment.status === 'approved' && toCents(payment.refunded_amount) === 0
              const label = payment.provider_reference || payment.intent_reference || t(`methods.${payment.method}`)
              return [
                <TableRow key={payment.id}>
                  <TableCell className="num hidden text-xs text-muted @sm:table-cell">{formatDate(payment.business_date, 'd MMM', lang)}</TableCell>
                  <TableCell>
                    <span className="font-medium text-fg">{t(`methods.${payment.method}`)}</span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
                      {payment.provider_reference && <span className="num">{payment.provider_reference}</span>}
                      {payment.provider === 'simulated' && <span>{t('folio.simulated')}</span>}
                      {payment.notes && <span className="italic">{payment.notes}</span>}
                      <PaymentStatusBadge status={payment.status} className="@md:hidden" />
                    </span>
                  </TableCell>
                  <TableCell className="hidden @md:table-cell">
                    <PaymentStatusBadge status={payment.status} />
                  </TableCell>
                  <TableCell className="text-right font-semibold">
                    <MoneyText value={payment.amount} currency={currency} className={cn(payment.status !== 'approved' && 'text-subtle line-through')} />
                  </TableCell>
                  {hasActions && (
                    <TableCell className="px-1 text-right">
                      {(canRefund || canVoid || movable) && (
                        <RowMenu label={t('folio.paymentActions', { label })}>
                          {movable && (
                            <>
                              <DropdownMenuLabel className="text-xs font-semibold text-muted">{t('move.paymentTo')}</DropdownMenuLabel>
                              {moveTargets.map((target) => (
                                <DropdownMenuItem key={target.folio.id} onSelect={() => onMove?.(payment, target.folio)}>
                                  <ArrowRightLeft aria-hidden />
                                  {target.name}
                                </DropdownMenuItem>
                              ))}
                              {(canRefund || canVoid) && <DropdownMenuSeparator />}
                            </>
                          )}
                          {canRefund && (
                            <DropdownMenuItem onSelect={() => onRefund(payment)}>
                              <Undo2 aria-hidden />
                              {t('risk.refund')}
                            </DropdownMenuItem>
                          )}
                          {canVoid && (
                            <DropdownMenuItem destructive onSelect={() => onVoid(payment)}>
                              <Undo2 aria-hidden />
                              {t('risk.voidPaymentTitle')}
                            </DropdownMenuItem>
                          )}
                        </RowMenu>
                      )}
                    </TableCell>
                  )}
                </TableRow>,
                ...refundsOf(payment).map((refund) => (
                  <TableRow key={refund.id} className="bg-surface-2/40">
                    <TableCell className="num hidden text-xs text-muted @sm:table-cell">
                      {refund.business_date ? formatDate(refund.business_date, 'd MMM', lang) : ''}
                    </TableCell>
                    <TableCell>
                      <span className="pl-3 font-medium text-fg">↳ {t('folio.refund')}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 pl-3 text-xs text-muted">
                        <span className="italic">{refund.reason}</span>
                        {refund.error && <span className="text-danger-ink">{refund.error}</span>}
                        <PaymentStatusBadge status={refund.status} className="@md:hidden" />
                      </span>
                    </TableCell>
                    <TableCell className="hidden @md:table-cell">
                      <PaymentStatusBadge status={refund.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <MoneyText value={fromCents(-toCents(refund.amount))} currency={currency} className="text-muted" />
                    </TableCell>
                    {hasActions && (
                      <TableCell className="px-1 text-right">
                        {onComplete && refund.status === 'pending' && (
                          <RowMenu label={t('folio.refundActions')}>
                            <DropdownMenuItem onSelect={() => onComplete(refund)}>{t('risk.completeTitle')}</DropdownMenuItem>
                          </RowMenu>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                )),
              ]
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

function LinksList({
  intents,
  currency,
  canSync,
  onChange,
}: {
  intents: PaymentIntent[]
  currency: string
  canSync: boolean
  onChange: () => void
}) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const sync = useFinanceMutation((id: string) => syncIntent(id), {
    onSuccess: (intent) => {
      toast.message(t('links.checked', { status: t(`links.status.${intent.status}`) }))
      onChange()
    },
  })

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t('link.copied'))
    } catch {
      toast.message(url)
    }
  }

  return (
    <div className="grid gap-2">
      <SectionTitle title={t('links.title')} count={intents.length} />
      <ul className="divide-y divide-border rounded-lg border border-border">
        {intents.map((intent) => {
          const live = intent.status === 'created' || intent.status === 'pending'
          return (
            <li key={intent.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <MoneyText value={intent.amount} currency={currency} className="font-semibold" />
                  <LinkStatusBadge status={intent.status} />
                  {intent.mode === 'simulated' && <span className="text-xs text-muted">{t('folio.simulated')}</span>}
                </p>
                <p className="num mt-0.5 truncate text-xs text-muted">
                  {intent.reference}
                  {live && intent.expires_at && ` · ${t('links.expires', { when: formatRelative(intent.expires_at, lang) })}`}
                </p>
              </div>
              {live && (
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon-sm" aria-label={t('link.copy')} onClick={() => void copy(intent.checkout_url)}>
                    <Copy aria-hidden />
                  </Button>
                  <Button asChild variant="ghost" size="icon-sm">
                    <a href={intent.checkout_url} target="_blank" rel="noreferrer" aria-label={t('link.open')}>
                      <ExternalLink aria-hidden />
                    </a>
                  </Button>
                  {canSync && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t('links.verify')}
                      disabled={sync.isPending}
                      onClick={() => sync.mutate(intent.id)}
                    >
                      <RefreshCw aria-hidden className={cn(sync.isPending && sync.variables === intent.id && 'animate-spin')} />
                    </Button>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {sync.isError && <p className="text-xs text-danger-ink">{errorMessage(sync.error, t)}</p>}
    </div>
  )
}

export default FolioPanel
