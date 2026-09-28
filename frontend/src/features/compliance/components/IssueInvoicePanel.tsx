import type { TFunction } from 'i18next'
import { Building2, CircleCheck, FileText, ReceiptText, TriangleAlert, UserRound } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { errorMessage } from '@/lib/errors'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useIssueInvoice, useReservationLegal, type InvoiceCustomer, type InvoiceDetail, type LegalFolio, type ReservationLegal } from '../api'
import { InvoiceStatusBadge, SimulatedBadge } from './common'
import { useInvoiceFiles } from '../hooks'

/**
 * "Emitir factura": who the invoice goes to (P4: "Facturar a" — the guest or each company folio, one invoice per
 * folio), what will be invoiced (customer, lines, VAT or exemption, total), then the result with its PDF.
 * Used by the reservation action and by the reservation's Legal tab (`folioId` preselects a customer).
 */
export function IssueInvoicePanel({
  reservationId,
  onClose,
  folioId,
}: {
  reservationId: string
  onClose: () => void
  folioId?: string
}) {
  const legal = useReservationLegal(reservationId)
  const [result, setResult] = useState<InvoiceDetail | null>(null)

  if (result) return <IssueResult result={result} onClose={onClose} />
  if (legal.isPending) return <LoadingState variant="rows" rows={4} className="p-0" />
  if (legal.isError) return <ErrorState error={legal.error} onRetry={() => void legal.refetch()} />
  return <IssueForm reservationId={reservationId} data={legal.data} initialFolio={folioId} onClose={onClose} onIssued={setResult} />
}

function IssueResult({ result, onClose }: { result: InvoiceDetail; onClose: () => void }) {
  const { t } = useTranslation('compliance')
  const files = useInvoiceFiles()
  const ok = result.status === 'accepted' || result.status === 'issued'
  return (
    <div className="grid gap-4">
      <div className={ok ? 'flex gap-3 rounded-lg bg-success-soft p-3' : 'flex gap-3 rounded-lg bg-danger-soft p-3'}>
        {ok ? (
          <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-success-ink" />
        ) : (
          <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-danger-ink" />
        )}
        <div className="grid gap-1" role="status">
          <p className="flex flex-wrap items-center gap-2 font-semibold text-fg">
            <span className="num">{result.number}</span>
            <InvoiceStatusBadge status={result.status} />
            <SimulatedBadge mode={result.mode} />
          </p>
          <p className="text-[13px] text-muted">
            {ok ? t('issue.doneTo', { customer: result.customer_name }) : result.error_message || t('issue.failed')}
          </p>
          {result.cufe && <p className="truncate font-mono text-[11px] text-muted">CUFE {result.cufe}</p>}
        </div>
      </div>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button onClick={onClose}>{t('common:actions.close')}</Button>
        {ok && (
          <Button variant="primary" loading={files.busy === 'pdf'} onClick={() => void files.openPdf(result)}>
            <FileText aria-hidden />
            {t('invoice.viewPdf')}
          </Button>
        )}
      </div>
    </div>
  )
}

function customerDocument(customer: InvoiceCustomer, t: TFunction): string {
  if (customer.is_final_consumer) return t('invoice.finalConsumer', { id: customer.document_number })
  const type = t(`documentTypes.${customer.document_type}`, { defaultValue: customer.document_type })
  return `${type} ${customer.document_number}${customer.dv ? `-${customer.dv}` : ''}`
}

function IssueForm({
  reservationId,
  data,
  initialFolio,
  onClose,
  onIssued,
}: {
  reservationId: string
  data: ReservationLegal
  initialFolio?: string
  onClose: () => void
  onIssued: (invoice: InvoiceDetail) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const issue = useIssueInvoice()
  const canInvoice = useCan('compliance.invoice')
  const rows: LegalFolio[] = (data.folios ?? []).filter((row) => row.can_issue && row.preview)
  const [selected, setSelected] = useState<string | null>(
    rows.find((row) => row.folio_id === initialFolio)?.folio_id ?? rows[0]?.folio_id ?? null,
  )
  const [error, setError] = useState<string | null>(null)
  const row = rows.find((item) => item.folio_id === selected) ?? rows[0]
  const preview = row?.preview ?? data.preview
  const blocked = data.resolution.status === 'missing' || data.resolution.status === 'critical'

  if (!preview || (data.folios && rows.length === 0)) {
    return (
      <div className="grid gap-4">
        <div className="flex gap-3 rounded-lg border border-border bg-surface-2/60 p-3">
          <ReceiptText aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
          <div>
            <p className="font-semibold text-fg">{t('issue.nothing')}</p>
            <p className="text-[13px] text-muted">{data.has_accepted_invoice ? t('issue.nothingInvoiced') : t('issue.nothingHint')}</p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      </div>
    )
  }

  const customer = preview.customer
  const isCompany = Boolean(customer.company_id)
  return (
    <div className="grid gap-4">
      {rows.length > 1 && (
        <fieldset className="grid min-w-0 gap-2">
          <legend className="mb-1 text-[13px] font-semibold text-fg">{t('issue.billTo')}</legend>
          <RadioGroup value={row?.folio_id} onValueChange={setSelected} className="grid grid-cols-1 gap-2">
            {rows.map((item) => {
              const company = item.folio_type === 'company'
              const Icon = company ? Building2 : UserRound
              const active = item.folio_id === row?.folio_id
              return (
                <label
                  key={item.folio_id}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                    active ? 'border-accent/50 bg-accent-soft/60' : 'border-border hover:border-border-strong',
                  )}
                >
                  <RadioGroupItem value={item.folio_id} className="mt-1" />
                  <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', active ? 'text-accent-ink' : 'text-muted')} />
                  <span className="grid min-w-0 flex-1 gap-0.5">
                    <span className="flex flex-wrap items-center gap-2 text-[13px] font-semibold text-fg">
                      <span className="truncate">{item.customer.name}</span>
                      <Badge tone={company ? 'info' : 'neutral'}>{t(company ? 'issue.companyFolio' : 'issue.guestFolio')}</Badge>
                    </span>
                    <span className="num truncate text-xs text-muted">
                      {customerDocument(item.customer, t)} · {t('legal.uninvoiced', { count: item.uninvoiced.count })}
                    </span>
                  </span>
                  <MoneyText value={item.uninvoiced.total} className="text-[13px] font-semibold" />
                </label>
              )
            })}
          </RadioGroup>
        </fieldset>
      )}

      <div className="grid gap-1 rounded-lg border border-border p-3">
        <p className="eyebrow">{t('invoice.customer')}</p>
        <p className="font-semibold text-fg">{customer.name}</p>
        <p className="num text-[13px] text-muted">{customerDocument(customer, t)}</p>
        {isCompany && (
          <p className="text-xs text-muted">
            {customer.vat_responsible ? t('issue.vatResponsible') : t('issue.notVatResponsible')}
            {customer.tax_responsibilities?.length ? ` · ${customer.tax_responsibilities.join(' · ')}` : ''}
          </p>
        )}
        {isCompany && customer.payment_form === 'credit' && (
          <p className="text-xs font-semibold text-info-ink">{t('issue.onCredit', { count: customer.payment_terms_days ?? 0 })}</p>
        )}
        {customer.is_final_consumer && <p className="text-xs text-warning-ink">{t('issue.finalConsumerHint')}</p>}
      </div>

      <ul className="grid gap-1.5 text-[13px]" aria-label={t('invoice.lines')}>
        {preview.lines.map((line, index) => (
          <li key={`${line.code}-${index}`} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 text-fg">
              {line.description}
              <span className="ml-1.5 text-xs text-muted">
                {line.tax_status === 'exempt'
                  ? t('invoice.exempt')
                  : line.tax_status === 'excluded'
                    ? t('invoice.excluded')
                    : t('invoice.vatShort', { rate: formatNumber(Number(line.tax_rate), lang) })}
              </span>
            </span>
            <MoneyText value={line.total} />
          </li>
        ))}
        <li className="mt-1 flex items-baseline justify-between gap-3 border-t border-border pt-2 text-muted">
          <span>{t('issue.taxes')}</span>
          <MoneyText value={preview.tax_total} />
        </li>
        <li className="flex items-baseline justify-between gap-3 text-[15px] font-bold text-fg">
          <span>{t('invoice.total')}</span>
          <MoneyText value={preview.total} className="text-accent-ink" />
        </li>
      </ul>

      {preview.exempt_note && <p className="rounded-md bg-accent-soft px-3 py-2 text-[13px] text-accent-ink">{preview.exempt_note}</p>}
      {blocked && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
          {t(`resolution.advice.${data.resolution.status}`)}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
          {error}
        </p>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
        <p className="text-xs text-muted sm:mr-auto">
          {t('issue.numbering', { prefix: data.resolution.prefix || '—', number: data.resolution.next_number ?? '—' })}
        </p>
        <Button onClick={onClose} disabled={issue.isPending}>
          {t('common:actions.cancel')}
        </Button>
        <Button
          variant="primary"
          disabled={!canInvoice || blocked}
          loading={issue.isPending}
          onClick={async () => {
            setError(null)
            try {
              const invoice = await issue.mutateAsync(row ? { folio_id: row.folio_id } : { reservation_id: reservationId })
              onIssued(invoice)
              if (invoice.status === 'accepted' || invoice.status === 'issued') toast.success(t('issue.toast', { number: invoice.number }))
            } catch (err) {
              setError(errorMessage(err, t))
            }
          }}
        >
          <ReceiptText aria-hidden />
          {isCompany ? t('issue.submitCompany') : t('issue.submit')}
        </Button>
      </div>
    </div>
  )
}
