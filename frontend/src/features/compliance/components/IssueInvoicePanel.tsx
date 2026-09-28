import { CircleCheck, FileText, ReceiptText, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useIssueInvoice, useReservationLegal, type InvoiceDetail } from '../api'
import { InvoiceStatusBadge, SimulatedBadge } from './common'
import { useInvoiceFiles } from '../hooks'

/**
 * "Emitir factura": what will be invoiced (customer, lines, VAT or exemption, total), then the result with its PDF.
 * Used by the reservation action and by the reservation's Legal tab.
 */
export function IssueInvoicePanel({ reservationId, onClose }: { reservationId: string; onClose: () => void }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const legal = useReservationLegal(reservationId)
  const issue = useIssueInvoice()
  const files = useInvoiceFiles()
  const canInvoice = useCan('compliance.invoice')
  const [result, setResult] = useState<InvoiceDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (result) {
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
              {ok ? t('issue.done') : result.error_message || t('issue.failed')}
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

  if (legal.isPending) return <LoadingState variant="rows" rows={4} className="p-0" />
  if (legal.isError) return <ErrorState error={legal.error} onRetry={() => void legal.refetch()} />

  const data = legal.data
  const preview = data.preview
  const blocked = data.resolution.status === 'missing' || data.resolution.status === 'critical'

  if (!data.can_issue || !preview) {
    return (
      <div className="grid gap-4">
        <div className="flex gap-3 rounded-lg border border-border bg-surface-2/60 p-3">
          <ReceiptText aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
          <div>
            <p className="font-semibold text-fg">{t('issue.nothing')}</p>
            <p className="text-[13px] text-muted">
              {data.has_accepted_invoice ? t('issue.nothingInvoiced') : t('issue.nothingHint')}
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      </div>
    )
  }

  const customer = preview.customer
  return (
    <div className="grid gap-4">
      <div className="grid gap-1 rounded-lg border border-border p-3">
        <p className="eyebrow">{t('invoice.customer')}</p>
        <p className="font-semibold text-fg">{customer.name}</p>
        <p className="num text-[13px] text-muted">
          {customer.is_final_consumer
            ? t('invoice.finalConsumer', { id: customer.document_number })
            : `${t(`documentTypes.${customer.document_type}`, { defaultValue: customer.document_type })} ${customer.document_number}`}
        </p>
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
              const invoice = await issue.mutateAsync({ reservation_id: reservationId })
              setResult(invoice)
              if (invoice.status === 'accepted' || invoice.status === 'issued') toast.success(t('issue.toast', { number: invoice.number }))
            } catch (err) {
              setError(errorMessage(err, t))
            }
          }}
        >
          <ReceiptText aria-hidden />
          {t('issue.submit')}
        </Button>
      </div>
    </div>
  )
}
