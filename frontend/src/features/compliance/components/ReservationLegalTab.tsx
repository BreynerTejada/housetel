import { FileText, IdCard, PlaneLanding, PlaneTakeoff, ReceiptText, TriangleAlert, UserPen } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useRegisterTra, useReservationLegal } from '../api'
import { InvoiceStatusBadge, MissingFields, SectionTitle, SimulatedBadge, SireStatusBadge, TraStatusBadge } from './common'
import { useInvoiceFiles } from '../hooks'
import { InvoiceSheet } from './InvoiceSheet'
import { IssueInvoicePanel } from './IssueInvoicePanel'
import { RetryTraButton } from './TraTab'

/**
 * Reservation detail tab "Legal": its electronic invoice(s), the TRA registration of each guest, the SIRE movements
 * of foreign guests and what is still missing, with the actions that settle it.
 */
export function ReservationLegalTab({ reservationId }: { reservationId: string }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const legal = useReservationLegal(reservationId)
  const files = useInvoiceFiles()
  const register = useRegisterTra()
  const canInvoice = useCan('compliance.invoice')
  const canTra = useCan('compliance.tra')
  const [issuing, setIssuing] = useState(false)
  const [openInvoice, setOpenInvoice] = useState<string | null>(null)

  if (legal.isPending) return <LoadingState variant="rows" rows={4} />
  if (legal.isError) return <ErrorState error={legal.error} onRetry={() => void legal.refetch()} />
  const data = legal.data

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6">
      {data.warnings.length > 0 && (
        <ul className="grid gap-2">
          {data.warnings.map((warning) => (
            <li key={warning} className="flex gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5 text-[13px] text-warning-ink">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span>{t(`legal.warnings.${warning}`)}</span>
              {warning === 'final_consumer' && (
                <Link to={`/app/guests/${data.reservation.booker.id}`} className="ml-auto shrink-0 font-semibold underline">
                  {t('missing.fix')}
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      <section className="grid gap-3" aria-labelledby="legal-invoices">
        <SectionTitle id="legal-invoices" title={t('legal.invoices')} count={data.invoices.length} />
        {data.invoices.length > 0 && (
          <ul className="grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
            {data.invoices.map((invoice) => (
              <li key={invoice.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <button type="button" onClick={() => setOpenInvoice(invoice.id)} className="grid gap-0.5 text-left">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="num font-semibold text-fg hover:underline">{invoice.number || t('invoice.draft')}</span>
                    {invoice.kind === 'credit_note' && <Badge tone="outline">{t('invoice.kinds.short.credit_note')}</Badge>}
                    <InvoiceStatusBadge status={invoice.status} />
                    <SimulatedBadge mode={invoice.mode} />
                  </span>
                  <span className="text-xs text-muted">
                    {formatDate(invoice.issue_date, undefined, lang)} · {invoice.customer_name}
                    {invoice.is_exempt && ` · ${t('invoice.exempt')}`}
                  </span>
                </button>
                <div className="flex items-center gap-2">
                  <MoneyText value={invoice.total} className="font-semibold" />
                  <Button size="sm" variant="ghost" loading={files.busy === 'pdf'} onClick={() => void files.openPdf(invoice)}>
                    {files.busy !== 'pdf' && <FileText aria-hidden />}
                    PDF
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {data.can_issue ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-border-strong bg-surface-2/50 px-4 py-3">
            <div>
              <p className="text-[13px] font-semibold text-fg">
                {t('legal.uninvoiced', { count: data.uninvoiced.count })} · <MoneyText value={data.uninvoiced.total} />
              </p>
              <p className="text-xs text-muted">
                {data.reservation.status === 'checked_out' ? t('legal.uninvoicedDeparted') : t('legal.uninvoicedHint')}
              </p>
            </div>
            {canInvoice && (
              <Button variant="primary" onClick={() => setIssuing(true)}>
                <ReceiptText aria-hidden />
                {t('issue.submit')}
              </Button>
            )}
          </div>
        ) : (
          data.invoices.length === 0 && <p className="text-[13px] text-muted">{t('legal.noCharges')}</p>
        )}
      </section>

      <section className="grid gap-3" aria-labelledby="legal-tra">
        <SectionTitle id="legal-tra" title={t('legal.tra')} count={data.tra.length} />
        {data.tra.length === 0 && data.tra_candidates.length === 0 && <p className="text-[13px] text-muted">{t('legal.traNone')}</p>}
        {data.tra.length > 0 && (
          <ul className="grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
            {data.tra.map((registration) => (
              <li key={registration.id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                <div className="grid gap-1">
                  <p className="flex flex-wrap items-center gap-2 text-[13px]">
                    <IdCard aria-hidden className="size-4 text-muted" />
                    <span className="font-semibold text-fg">{registration.guest.full_name}</span>
                    <Badge tone={registration.is_main ? 'info' : 'neutral'}>{t(registration.is_main ? 'tra.main' : 'tra.companion')}</Badge>
                    <TraStatusBadge status={registration.status} />
                  </p>
                  <p className="num text-xs text-muted">
                    {registration.tra_number || t('tra.noNumber')}
                    {registration.room && ` · ${t('pending.room', { room: registration.room })}`}
                  </p>
                  <MissingFields fields={registration.missing_fields} scope="tra" />
                  {registration.status === 'error' && <p className="text-xs text-danger-ink">{registration.error}</p>}
                </div>
                {registration.status !== 'registered' && (
                  <div className="flex gap-1.5">
                    {registration.missing_fields.length > 0 && (
                      <Button asChild size="sm" variant="ghost">
                        <Link to={`/app/guests/${registration.guest.id}`}>
                          <UserPen aria-hidden />
                          {t('missing.fix')}
                        </Link>
                      </Button>
                    )}
                    <RetryTraButton registration={registration} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {data.tra_candidates.map((candidate) => (
          <div
            key={candidate.stay_id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-border-strong px-4 py-3"
          >
            <div>
              <p className="text-[13px] font-semibold text-fg">
                {t('legal.traCandidate', { room: candidate.room || '—', date: formatDate(candidate.checkin_date, undefined, lang) })}
              </p>
              <p className="text-xs text-muted">
                {candidate.guests.length ? candidate.guests.join(', ') : t('pending.noOccupants')}
              </p>
            </div>
            {canTra && candidate.guests.length > 0 && (
              <Button
                size="sm"
                loading={register.isPending}
                onClick={async () => {
                  try {
                    const rows = await register.mutateAsync(candidate.stay_id)
                    toast.success(t('pending.traDone', { count: rows.filter((row) => row.status === 'registered').length, total: rows.length }))
                  } catch (error) {
                    toast.error(errorMessage(error, t))
                  }
                }}
              >
                {t('pending.register')}
              </Button>
            )}
          </div>
        ))}
      </section>

      <section className="grid gap-3" aria-labelledby="legal-sire">
        <SectionTitle id="legal-sire" title={t('legal.sire')} count={data.sire.length} />
        {data.sire.length === 0 ? (
          <p className="text-[13px] text-muted">
            {data.reservation.booker.nationality && data.reservation.booker.nationality !== 'CO'
              ? t('legal.sireNotYet')
              : t('legal.sireNotApplicable')}
          </p>
        ) : (
          <ul className="grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
            {data.sire.map((record) => {
              const Icon = record.movement === 'E' ? PlaneLanding : PlaneTakeoff
              return (
                <li key={record.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-[13px]">
                  <div className="flex items-center gap-2.5">
                    <Icon aria-hidden className="size-4 text-muted" />
                    <div>
                      <p className="font-semibold text-fg">{record.guest_name}</p>
                      <p className="text-xs text-muted">
                        {t(`sire.movement.${record.movement}`)} · {formatDate(record.movement_date, undefined, lang)}
                      </p>
                      {!record.complete && <MissingFields fields={record.missing_fields} scope="sire" />}
                    </div>
                  </div>
                  <SireStatusBadge status={record.report_status} />
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <Dialog open={issuing} onOpenChange={setIssuing}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('issue.title')}</DialogTitle>
            <DialogDescription>{t('issue.description', { code: data.reservation.code })}</DialogDescription>
          </DialogHeader>
          {issuing && <IssueInvoicePanel reservationId={reservationId} onClose={() => setIssuing(false)} />}
        </DialogContent>
      </Dialog>
      <InvoiceSheet invoiceId={openInvoice} onOpenChange={(open) => !open && setOpenInvoice(null)} />
    </div>
  )
}
