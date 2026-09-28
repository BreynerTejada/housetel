import { CalendarClock, Download, FilePlus2, HandCoins, Landmark, MoreHorizontal, ReceiptText, Undo2, Wallet } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { DangerConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { saveBlob } from '@/features/finance/download'
import { fromCents, moneyLabel, plainAmount, toCents } from '@/features/finance/money'
import { downloadStatementCsv, useStatement, useVoidAccountPayment, type AccountPaymentRow, type Statement, type StatementItem } from '../api'
import { AccountPaymentDialog } from './AccountPaymentDialog'
import { AGING_FILL } from '../lib/aging'
import { AgingRibbon } from './AgingRibbon'
import { OpeningBalanceDialog } from './OpeningBalanceDialog'

type OpenDialog = { type: 'payment' } | { type: 'credit' } | { type: 'opening' } | { type: 'void'; payment: AccountPaymentRow }

/** The company's account statement at this hotel: what it owes, how old it is, and what it paid. */
export function StatementPanel({ companyId }: { companyId: string }) {
  const statement = useStatement(companyId)
  if (statement.isPending) return <LoadingState variant="rows" rows={6} />
  if (statement.isError) return <ErrorState error={statement.error} onRetry={() => void statement.refetch()} />
  return <StatementView companyId={companyId} statement={statement.data} />
}

function StatementView({ companyId, statement }: { companyId: string; statement: Statement }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  const canAr = useCan('corporate.ar')
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const [exporting, setExporting] = useState(false)
  const currency = statement.currency
  const totals = statement.totals
  const net = toCents(totals.net_balance)
  const inFavor = net < 0
  const close = () => setDialog(null)

  async function exportCsv() {
    setExporting(true)
    try {
      saveBlob(await downloadStatementCsv(companyId), `estado-de-cuenta-${statement.company.nit}-${statement.as_of}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setExporting(false)
    }
  }

  return (
    <section aria-label={t('statement.region')} className="@container overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
      <div className="grid gap-5 px-5 pt-5 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow">{inFavor ? t('statement.inFavor') : t('statement.netBalance')}</p>
            <p className={cn('num mt-1 text-[34px] leading-10 font-semibold tracking-[-0.035em]', inFavor ? 'text-info-ink' : 'text-fg')}>
              <MoneyText value={fromCents(Math.abs(net))} currency={currency} />
            </p>
            <p className="mt-1 text-[13px] text-muted">
              {t('statement.asOf', { date: formatDate(statement.as_of, undefined, lang) })}
              {toCents(totals.unapplied) > 0 && ` · ${t('statement.netHint', { amount: moneyLabel(totals.unapplied, currency) })}`}
            </p>
          </div>
          <div className="grid w-full grid-cols-2 gap-2 @xl:flex @xl:w-auto @xl:flex-wrap @xl:items-center">
            <Button variant="secondary" className="w-full @xl:w-auto" loading={exporting} onClick={() => void exportCsv()}>
              {!exporting && <Download aria-hidden />}
              {t('statement.export')}
            </Button>
            {canAr && toCents(totals.unapplied) > 0 && toCents(totals.balance) > 0 && (
              <Button variant="secondary" className="w-full @xl:w-auto" onClick={() => setDialog({ type: 'credit' })}>
                <HandCoins aria-hidden />
                {t('statement.applyCredit')}
              </Button>
            )}
            {canAr && (
              <Button variant="primary" className="order-first col-span-2 w-full @xl:order-none @xl:w-auto" onClick={() => setDialog({ type: 'payment' })}>
                <Wallet aria-hidden />
                {t('statement.recordPayment')}
              </Button>
            )}
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 @lg:grid-cols-4">
          <Figure label={t('statement.balance')} value={totals.balance} currency={currency} />
          <Figure
            label={t('statement.overdue')}
            value={totals.overdue}
            currency={currency}
            tone={toCents(totals.overdue) > 0 ? 'text-danger-ink' : undefined}
          />
          <Figure label={t('statement.unapplied')} value={totals.unapplied} currency={currency} />
          <Figure label={t('statement.inProgress')} value={totals.in_progress} currency={currency} hint={t('statement.inProgressHint')} />
        </dl>

        {toCents(totals.balance) > 0 && <AgingRibbon aging={statement.aging} currency={currency} />}
      </div>

      <Perforation />

      <div className="grid gap-7 px-5 pt-1 pb-6">
        <ItemsTable items={statement.items} currency={currency} />
        {statement.in_progress.length > 0 && <InProgressList items={statement.in_progress} currency={currency} />}
        <PaymentsList
          payments={statement.payments}
          currency={currency}
          onVoid={canAr ? (payment) => setDialog({ type: 'void', payment }) : undefined}
          footer={
            canAr && (
              <Button variant="ghost" size="sm" className="w-fit" onClick={() => setDialog({ type: 'opening' })}>
                <FilePlus2 aria-hidden />
                {t('statement.addOpening')}
              </Button>
            )
          }
        />
      </div>

      <AccountPaymentDialog
        open={dialog?.type === 'payment' || dialog?.type === 'credit'}
        onOpenChange={(value) => !value && close()}
        companyId={companyId}
        statement={statement}
        mode={dialog?.type === 'credit' ? 'credit' : 'payment'}
      />
      <OpeningBalanceDialog
        open={dialog?.type === 'opening'}
        onOpenChange={(value) => !value && close()}
        companyId={companyId}
        companyName={statement.company.legal_name}
      />
      {dialog?.type === 'void' && <VoidPaymentDialog payment={dialog.payment} currency={currency} onClose={close} />}
    </section>
  )
}

function Figure({ label, value, currency, tone, hint }: { label: string; value: string; currency: string; tone?: string; hint?: string }) {
  return (
    <div className="grid gap-0.5" title={hint}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={cn('text-sm font-semibold', tone)}>
        <MoneyText value={value} currency={currency} />
      </dd>
    </div>
  )
}

/** The torn edge between the stub and the ledger, like the folio: the statement reads as a document. */
function Perforation() {
  return (
    <div aria-hidden className="relative h-6">
      <span className="absolute top-1/2 -left-3 size-6 -translate-y-1/2 rounded-full border border-border bg-bg" />
      <span className="absolute inset-x-5 top-1/2 border-t-[1.5px] border-dashed border-border-strong" />
      <span className="absolute top-1/2 -right-3 size-6 -translate-y-1/2 rounded-full border border-border bg-bg" />
    </div>
  )
}

function SectionTitle({ title, count }: { title: string; count?: number }) {
  return (
    <h3 className="flex items-baseline gap-2 text-[15px] font-bold">
      {title}
      {count !== undefined && <span className="num text-xs font-semibold text-subtle">{count}</span>}
    </h3>
  )
}

function DocumentCell({ item }: { item: StatementItem }) {
  const { t } = useTranslation('corporate')
  const Icon = item.kind === 'opening_balance' ? Landmark : ReceiptText
  return (
    <div className="grid min-w-0 gap-0.5">
      <span className="flex min-w-0 items-center gap-1.5 font-medium text-fg">
        <Icon aria-hidden className="size-3.5 shrink-0 text-muted" />
        <span className="num truncate">{item.invoice?.number || item.label || t('statement.noInvoice')}</span>
      </span>
      <span className="truncate text-xs text-muted">
        {item.reservation ? (
          <>
            <Link to={`/app/reservations/${item.reservation.id}?tab=folio`} className="num hover:text-fg hover:underline">
              {item.reservation.code}
            </Link>
            {` · ${item.reservation.guest_name}`}
          </>
        ) : (
          t('statement.openingBalance')
        )}
      </span>
    </div>
  )
}

function ItemsTable({ items, currency }: { items: StatementItem[]; currency: string }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="grid gap-2">
      <SectionTitle title={t('statement.items')} count={items.length} />
      {items.length === 0 ? (
        <EmptyState icon={ReceiptText} title={t('statement.noItems')} description={t('statement.noItemsHint')} className="py-8" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>{t('statement.document')}</TableHead>
              <TableHead className="hidden @md:table-cell">{t('statement.date')}</TableHead>
              <TableHead className="hidden @lg:table-cell">{t('statement.due')}</TableHead>
              <TableHead className="hidden text-right @2xl:table-cell">{t('statement.total')}</TableHead>
              <TableHead className="hidden text-right @2xl:table-cell">{t('statement.paid')}</TableHead>
              <TableHead className="text-right">{t('statement.balanceColumn')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.folio_id}>
                <TableCell className="max-w-0 min-w-40">
                  <DocumentCell item={item} />
                  <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted @md:hidden">
                    {item.document_date && formatDate(item.document_date, 'd MMM', lang)}
                    <AgeChip item={item} />
                  </span>
                </TableCell>
                <TableCell className="num hidden text-xs text-muted @md:table-cell">
                  <span className="flex items-center gap-2">
                    <span aria-hidden className={cn('size-2 shrink-0 rounded-[2px]', AGING_FILL[item.bucket])} />
                    {item.document_date ? formatDate(item.document_date, 'd MMM yyyy', lang) : '—'}
                  </span>
                </TableCell>
                <TableCell className="hidden @lg:table-cell">
                  <span className="grid gap-0.5">
                    <span className="num text-xs text-muted">{item.due_date ? formatDate(item.due_date, 'd MMM yyyy', lang) : '—'}</span>
                    <AgeChip item={item} />
                  </span>
                </TableCell>
                <TableCell className="hidden text-right @2xl:table-cell">
                  <MoneyText value={item.charges_total} currency={currency} className="text-muted" />
                </TableCell>
                <TableCell className="hidden text-right @2xl:table-cell">
                  <MoneyText value={item.paid} currency={currency} className="text-muted" />
                </TableCell>
                <TableCell className="text-right font-semibold">
                  <MoneyText value={item.balance} currency={currency} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

function AgeChip({ item }: { item: StatementItem }) {
  const { t } = useTranslation('corporate')
  if (item.overdue_days > 0) {
    return <Badge tone="danger">{t('statement.overdueDays', { count: item.overdue_days })}</Badge>
  }
  return <span className="text-xs text-muted">{t('statement.ageDays', { count: item.age_days })}</span>
}

function InProgressList({ items, currency }: { items: StatementItem[]; currency: string }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="grid gap-2">
      <SectionTitle title={t('statement.inProgressTitle')} count={items.length} />
      <p className="text-xs text-muted">{t('statement.inProgressExplain')}</p>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {items.map((item) => (
          <li key={item.folio_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-2.5 text-[13px]">
            <span className="flex min-w-0 items-center gap-2">
              <CalendarClock aria-hidden className="size-4 shrink-0 text-muted" />
              {item.reservation ? (
                <span className="min-w-0">
                  <Link to={`/app/reservations/${item.reservation.id}?tab=corporate-billing`} className="num font-semibold text-fg hover:underline">
                    {item.reservation.code}
                  </Link>
                  <span className="text-muted">
                    {` · ${item.reservation.guest_name} · ${formatDate(item.reservation.checkin_date, 'd MMM', lang)}–${formatDate(item.reservation.checkout_date, 'd MMM', lang)}`}
                  </span>
                </span>
              ) : (
                <span className="font-semibold text-fg">{item.label}</span>
              )}
            </span>
            <MoneyText value={item.expected_balance} currency={currency} className="font-semibold" />
          </li>
        ))}
      </ul>
    </div>
  )
}

function PaymentsList({
  payments,
  currency,
  onVoid,
  footer,
}: {
  payments: AccountPaymentRow[]
  currency: string
  onVoid?: (payment: AccountPaymentRow) => void
  footer?: ReactNode
}) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="grid gap-2">
      <SectionTitle title={t('statement.payments')} count={payments.length} />
      {payments.length === 0 ? (
        <p className="py-2 text-[13px] text-muted">{t('statement.noPayments')}</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {payments.map((payment) => {
            const voided = payment.status === 'voided'
            return (
              <li key={payment.id} className="grid gap-2 px-3 py-3 text-[13px]">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="grid min-w-0 gap-0.5">
                    <p className="flex flex-wrap items-center gap-2">
                      <MoneyText value={payment.amount} currency={currency} className={cn('font-semibold', voided && 'text-subtle line-through')} />
                      <span className="text-muted">{t(`methods.${payment.method}`)}</span>
                      {payment.reference && <span className="num text-muted">{payment.reference}</span>}
                      {voided && <Badge tone="stone">{t('statement.voided')}</Badge>}
                      {!voided && toCents(payment.unapplied) > 0 && (
                        <Badge tone="info">{t('statement.unappliedBadge', { amount: moneyLabel(payment.unapplied, currency) })}</Badge>
                      )}
                    </p>
                    <p className="text-xs text-muted">
                      {t('statement.receivedOn', { date: formatDate(payment.received_on, undefined, lang) })}
                      {payment.created_by && ` · ${payment.created_by}`}
                      {voided && payment.void_reason && ` · ${payment.void_reason}`}
                    </p>
                  </div>
                  {onVoid && !voided && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={t('statement.paymentActions')}>
                          <MoreHorizontal aria-hidden />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem destructive onSelect={() => onVoid(payment)}>
                          <Undo2 aria-hidden />
                          {t('statement.voidPayment')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
                {payment.allocations.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5" aria-label={t('statement.allocations')}>
                    {payment.allocations.map((allocation) => (
                      <li key={allocation.id} className="rounded-md bg-surface-2 px-2 py-0.5 text-xs text-muted">
                        <span className="num font-semibold text-fg">{allocation.reservation_code || allocation.label}</span>{' '}
                        <MoneyText value={allocation.amount} currency={currency} />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {footer}
    </div>
  )
}

function VoidPaymentDialog({ payment, currency, onClose }: { payment: AccountPaymentRow; currency: string; onClose: () => void }) {
  const { t } = useTranslation('corporate')
  const voidPayment = useVoidAccountPayment()
  const [reason, setReason] = useState('')
  return (
    <DangerConfirmDialog
      open
      onOpenChange={(value) => !value && onClose()}
      title={t('void.title', { amount: moneyLabel(payment.amount, currency) })}
      description={t('void.description')}
      confirmText={plainAmount(payment.amount, currency)}
      confirmLabel={t('void.confirm')}
      confirmDisabled={reason.trim().length < 3}
      onConfirm={async () => {
        await voidPayment.mutateAsync({ id: payment.id, reason: reason.trim() })
        toast.success(t('void.done'))
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor="void-reason">{t('void.reason')}</Label>
        <Textarea id="void-reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
      </div>
    </DangerConfirmDialog>
  )
}
