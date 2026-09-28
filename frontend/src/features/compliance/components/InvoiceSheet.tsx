import { Ban, ExternalLink, FileCode, FileText, RotateCcw, TriangleAlert } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { DangerConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useCreditNote, useInvoice, useRetryInvoice, type InvoiceDetail, type InvoiceLine } from '../api'
import { useInvoiceFiles } from '../hooks'
import { hashGroups, RETRYABLE, VOIDABLE } from '../lib/labels'
import { CopyButton, InvoiceStatusBadge, SimulatedBadge } from './common'

/** Perforated top edge of the paper (the key-tag perforation motif of Housetel's brand). */
const PERFORATION = {
  backgroundImage: 'radial-gradient(circle at 7px 0, var(--bg) 3.5px, transparent 4px)',
  backgroundSize: '14px 8px',
  backgroundRepeat: 'repeat-x',
} as const

const STAMP_TONE: Record<string, string> = {
  accepted: 'border-success text-success-ink',
  issued: 'border-info text-info-ink',
  cancelled: 'border-stone text-stone-ink',
  rejected: 'border-danger text-danger-ink',
  error: 'border-warning text-warning-ink',
  draft: 'border-border-strong text-muted',
}

function taxLabel(line: InvoiceLine, t: (key: string) => string, lang: 'es' | 'en') {
  if (line.tax_status === 'exempt') return t('invoice.exempt')
  if (line.tax_status === 'excluded') return t('invoice.excluded')
  return `${formatNumber(Number(line.tax_rate), lang)} %`
}

function Paper({ invoice }: { invoice: InvoiceDetail }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const customer = invoice.customer
  const byStatus = invoice.lines.reduce<Record<string, number>>((acc, line) => {
    acc[line.tax_status] = (acc[line.tax_status] ?? 0) + Number(line.net)
    return acc
  }, {})
  const taxGroups = invoice.lines
    .filter((line) => line.tax_status === 'taxed')
    .reduce<Record<string, { base: number; tax: number }>>((acc, line) => {
      const group = (acc[line.tax_rate] ??= { base: 0, tax: 0 })
      group.base += Number(line.net)
      group.tax += Number(line.tax_amount)
      return acc
    }, {})

  return (
    <article aria-label={t('invoice.paper')} className="rounded-b-lg border border-t-0 border-border bg-surface shadow-xs">
      <div aria-hidden className="h-2 bg-surface-2" style={PERFORATION} />
      <div className="grid gap-5 p-4 sm:p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid content-start gap-0.5">
            <p className="eyebrow">{t('invoice.customer')}</p>
            <p className="font-semibold text-fg">{customer.name}</p>
            <p className="num text-[13px] text-muted">
              {customer.is_final_consumer
                ? t('invoice.finalConsumer', { id: customer.document_number })
                : `${t(`documentTypes.${customer.document_type}`, { defaultValue: customer.document_type })} ${customer.document_number}${customer.dv ? `-${customer.dv}` : ''}`}
            </p>
            {customer.email && <p className="truncate text-[13px] text-muted">{customer.email}</p>}
          </div>
          <div className="grid content-start gap-0.5 sm:text-right">
            <p className="eyebrow">{t('invoice.total')}</p>
            <MoneyText value={invoice.total} currency={invoice.currency} className="text-[26px] leading-8 font-semibold tracking-[-0.02em]" />
            <p className="text-[13px] text-muted">
              {t('invoice.issuedOn', { date: formatDate(invoice.issue_date, undefined, lang) })}
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <caption className="sr-only">{t('invoice.lines')}</caption>
            <thead>
              <tr className="border-b border-border text-left text-2xs font-bold tracking-[0.06em] text-muted uppercase">
                <th scope="col" className="py-1.5 pr-2 font-bold">{t('invoice.description')}</th>
                <th scope="col" className="hidden px-2 py-1.5 text-right font-bold sm:table-cell">{t('invoice.quantity')}</th>
                <th scope="col" className="px-2 py-1.5 text-right font-bold">{t('invoice.tax')}</th>
                <th scope="col" className="py-1.5 pl-2 text-right font-bold">{t('invoice.lineTotal')}</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line, index) => (
                <tr key={`${line.code}-${index}`} className="border-b border-border last:border-0">
                  <td className="py-2 pr-2">
                    <span className="text-fg">{line.description}</span>
                    <span className="block text-2xs text-subtle">{line.code}</span>
                  </td>
                  <td className="num hidden px-2 py-2 text-right sm:table-cell">{line.quantity}</td>
                  <td className={cn('px-2 py-2 text-right', line.tax_status === 'exempt' && 'font-semibold text-success-ink')}>
                    {taxLabel(line, t, lang)}
                  </td>
                  <td className="py-2 pl-2 text-right">
                    <MoneyText value={line.total} currency={invoice.currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-end justify-between gap-4">
          <span
            aria-hidden
            className={cn(
              'ml-2 rotate-[-7deg] rounded-md border-2 px-2.5 py-1 text-[11px] font-extrabold tracking-[0.16em] uppercase opacity-85 select-none',
              STAMP_TONE[invoice.status],
            )}
          >
            {t(`invoice.stamp.${invoice.status}`)}
          </span>
        <dl className="ml-auto grid w-full max-w-72 gap-1 text-[13px]">
          <div className="flex justify-between gap-4">
            <dt className="text-muted">{t('invoice.subtotal')}</dt>
            <dd><MoneyText value={invoice.subtotal} currency={invoice.currency} /></dd>
          </div>
          {byStatus.exempt ? (
            <div className="flex justify-between gap-4">
              <dt className="text-muted">{t('invoice.exemptBase')}</dt>
              <dd><MoneyText value={byStatus.exempt} currency={invoice.currency} /></dd>
            </div>
          ) : null}
          {byStatus.excluded ? (
            <div className="flex justify-between gap-4">
              <dt className="text-muted">{t('invoice.excludedBase')}</dt>
              <dd><MoneyText value={byStatus.excluded} currency={invoice.currency} /></dd>
            </div>
          ) : null}
          {Object.entries(taxGroups).map(([rate, group]) => (
            <div key={rate} className="flex justify-between gap-4">
              <dt className="text-muted">{t('invoice.vat', { rate: formatNumber(Number(rate), lang) })}</dt>
              <dd><MoneyText value={group.tax} currency={invoice.currency} /></dd>
            </div>
          ))}
          <div className="mt-1 flex justify-between gap-4 border-t border-accent pt-1.5 font-bold">
            <dt>{t('invoice.total')}</dt>
            <dd><MoneyText value={invoice.total} currency={invoice.currency} className="text-accent-ink" /></dd>
          </div>
        </dl>
        </div>

        {invoice.exempt_note && (
          <p className="rounded-md bg-accent-soft px-3 py-2 text-[13px] text-accent-ink">{invoice.exempt_note}</p>
        )}
      </div>
    </article>
  )
}

function Validation({ invoice }: { invoice: InvoiceDetail }) {
  const { t } = useTranslation('compliance')
  const code = invoice.kind === 'credit_note' ? 'CUDE' : 'CUFE'
  if (!invoice.cufe) {
    return <p className="rounded-lg border border-dashed border-border px-4 py-3 text-[13px] text-muted">{t('invoice.noCufe', { code })}</p>
  }
  return (
    <section aria-label={code} className="grid gap-4 rounded-lg border border-border bg-surface-2/60 p-4 sm:grid-cols-[auto_1fr]">
      <div className="w-fit rounded-md bg-white p-2 shadow-xs">
        <QRCodeSVG value={invoice.qr_data || invoice.validation_url} size={104} level="M" title={t('invoice.qr')} />
      </div>
      <div className="grid min-w-0 content-start gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="eyebrow">{code}</p>
          <CopyButton value={invoice.cufe} label={t('invoice.copyCufe', { code })} />
        </div>
        <p className="grid grid-cols-4 gap-x-2 gap-y-0.5 font-mono text-[11.5px] leading-5 text-fg sm:grid-cols-6" aria-label={invoice.cufe}>
          {hashGroups(invoice.cufe).map((group, index) => (
            <span key={index} aria-hidden>
              {group}
            </span>
          ))}
        </p>
        {invoice.validation_url && (
          <a
            href={invoice.validation_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-fit items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline"
          >
            {t('invoice.validate')}
            <ExternalLink aria-hidden className="size-3.5" />
          </a>
        )}
        {invoice.mode === 'simulated' && <p className="text-xs text-muted">{t('invoice.simulatedValidation')}</p>}
      </div>
    </section>
  )
}

function CreditNoteDialog({ invoice, open, onOpenChange }: { invoice: InvoiceDetail; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation('compliance')
  const reasonId = useId()
  const [reason, setReason] = useState('')
  const creditNote = useCreditNote()
  return (
    <DangerConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setReason('')
        onOpenChange(next)
      }}
      title={t('creditNote.title', { number: invoice.number })}
      description={t('creditNote.description')}
      confirmLabel={t('creditNote.confirm')}
      confirmText={invoice.number}
      confirmDisabled={reason.trim().length < 5}
      onConfirm={async () => {
        const note = await creditNote.mutateAsync({ id: invoice.id, reason: reason.trim() })
        toast.success(t('creditNote.done', { number: note.number }))
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={reasonId}>{t('creditNote.reason')}</Label>
        <Textarea
          id={reasonId}
          name="reason"
          rows={3}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t('creditNote.reasonPlaceholder')}
        />
        <p className="text-xs text-muted">{t('creditNote.hint')}</p>
      </div>
    </DangerConfirmDialog>
  )
}

/** Detail of one electronic invoice or credit note, drawn as the document itself, with its actions. */
export function InvoiceSheet({ invoiceId, onOpenChange }: { invoiceId: string | null; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const query = useInvoice(invoiceId)
  const retry = useRetryInvoice()
  const files = useInvoiceFiles()
  const canInvoice = useCan('compliance.invoice')
  const canVoid = useCan('compliance.void_invoice')
  const [voiding, setVoiding] = useState(false)
  const invoice = query.data

  const title = invoice ? t(`invoice.kinds.${invoice.kind}`) : t('invoice.loading')
  const hasOpenCreditNote = invoice?.credit_notes.some((note) => note.status !== 'rejected' && note.status !== 'error') ?? false

  return (
    <Sheet open={Boolean(invoiceId)} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(40rem,96vw)]">
        <SheetHeader>
          <p className="eyebrow">{title}</p>
          <SheetTitle className="num flex flex-wrap items-center gap-2 text-xl tracking-[-0.02em]">
            {invoice?.number || t('invoice.draft')}
            {invoice && <InvoiceStatusBadge status={invoice.status} />}
            {invoice && <SimulatedBadge mode={invoice.mode} />}
          </SheetTitle>
          <SheetDescription>
            {invoice ? (
              <>
                {invoice.issued_at ? formatDate(invoice.issued_at, lang === 'es' ? "d MMM yyyy, HH:mm" : 'MMM d, yyyy, HH:mm', lang) : '—'}
                {invoice.reservation_id && (
                  <>
                    {' · '}
                    <Link to={`/app/reservations/${invoice.reservation_id}`} className="font-semibold text-accent-ink hover:underline">
                      {t('invoice.reservation', { code: invoice.reservation_code })}
                    </Link>
                  </>
                )}
              </>
            ) : (
              '…'
            )}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="grid content-start gap-4">
          {query.isPending ? (
            <LoadingState variant="rows" rows={6} className="p-0" />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : (
            <>
              {(invoice!.status === 'error' || invoice!.status === 'rejected' || invoice!.status === 'draft') && invoice!.error_message && (
                <div role="alert" className="flex gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5 text-[13px] text-danger-ink">
                  <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <p className="font-semibold">{t(invoice!.status === 'rejected' ? 'invoice.rejected' : 'invoice.failed')}</p>
                    <p>{invoice!.error_message}</p>
                    <p className="mt-1 text-xs opacity-80">{t('invoice.attempts', { count: invoice!.attempts })}</p>
                  </div>
                </div>
              )}
              {invoice!.kind === 'credit_note' && (
                <div className="rounded-lg border border-border bg-surface-2/60 px-4 py-3 text-[13px]">
                  <p className="eyebrow">{t('creditNote.references')}</p>
                  <p className="mt-1 font-semibold text-fg">{t('creditNote.annuls', { number: invoice!.related_number })}</p>
                  {invoice!.reason && <p className="text-muted">{invoice!.reason}</p>}
                </div>
              )}
              <Paper invoice={invoice!} />
              <Validation invoice={invoice!} />
              {invoice!.credit_notes.length > 0 && (
                <div className="rounded-lg border border-border px-4 py-3 text-[13px]">
                  <p className="eyebrow">{t('creditNote.list')}</p>
                  <ul className="mt-1 grid gap-1">
                    {invoice!.credit_notes.map((note) => (
                      <li key={note.id} className="flex flex-wrap items-center gap-2">
                        <span className="num font-semibold">{note.number}</span>
                        <InvoiceStatusBadge status={note.status} />
                        <span className="text-muted">{note.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {invoice!.resolution && (
                <p className="text-xs text-muted">
                  {t('invoice.authorization', {
                    number: invoice!.resolution.resolution_number || '—',
                    prefix: invoice!.resolution.prefix || '—',
                    from: invoice!.resolution.from_number,
                    to: invoice!.resolution.to_number,
                    date: formatDate(invoice!.resolution.valid_to, undefined, lang),
                  })}
                </p>
              )}
            </>
          )}
        </SheetBody>
        {invoice && (
          <SheetFooter className="flex-wrap">
            <Button onClick={() => void files.openPdf(invoice)} loading={files.busy === 'pdf'}>
              <FileText aria-hidden />
              {t('invoice.viewPdf')}
            </Button>
            <Button variant="ghost" onClick={() => void files.download(invoice, 'xml')} loading={files.busy === 'xml'}>
              <FileCode aria-hidden />
              {t('invoice.xml')}
            </Button>
            {canInvoice && RETRYABLE.includes(invoice.status) && (
              <Button
                loading={retry.isPending}
                onClick={async () => {
                  try {
                    const result = await retry.mutateAsync(invoice.id)
                    toast.success(t('invoice.retried', { status: t(`invoiceStatus.${result.status}`) }))
                  } catch (error) {
                    toast.error(errorMessage(error, t))
                  }
                }}
              >
                <RotateCcw aria-hidden />
                {t(invoice.status === 'issued' ? 'invoice.refresh' : 'invoice.retry')}
              </Button>
            )}
            {canVoid && invoice.kind === 'invoice' && VOIDABLE.includes(invoice.status) && !hasOpenCreditNote && (
              <Button variant="danger" onClick={() => setVoiding(true)} className="sm:ml-auto">
                <Ban aria-hidden />
                {t('creditNote.action')}
              </Button>
            )}
          </SheetFooter>
        )}
        {invoice && <CreditNoteDialog invoice={invoice} open={voiding} onOpenChange={setVoiding} />}
      </SheetContent>
    </Sheet>
  )
}
