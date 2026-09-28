import { CircleCheck, Download, FileSpreadsheet, ReceiptText, RotateCcw, Upload, UserPen, UserPlus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import {
  useGenerateSire,
  useIssueInvoice,
  useRegisterTra,
  useRetryInvoice,
  type IntegrationMode,
  type PendingInvoice,
  type PendingSummary,
  type PendingTra,
} from '../api'
import { InvoiceStatusBadge, MissingFields, SectionTitle, TraStatusBadge } from './common'
import { ResolutionHealthCard } from './ResolutionHealth'
import { RetryTraButton } from './TraTab'
import { useSireDownload } from '../hooks'
import { MarkSubmittedDialog, MissingList } from './SireTab'

function Row({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
      <div className="grid min-w-0 gap-1">{children}</div>
      {actions && <div className="flex shrink-0 flex-wrap gap-1.5">{actions}</div>}
    </li>
  )
}

function Group({
  title,
  count,
  shown,
  children,
  empty,
}: {
  title: string
  count: number
  shown?: number
  children: ReactNode
  empty: string
}) {
  const { t } = useTranslation('compliance')
  return (
    <section className="grid gap-2">
      <SectionTitle title={title} count={count} />
      {shown !== undefined && shown < count && <p className="text-xs text-muted">{t('pending.showing', { shown, count })}</p>}
      {count === 0 ? (
        <p className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-3 text-[13px] text-muted">
          <CircleCheck aria-hidden className="size-4 text-success-ink" />
          {empty}
        </p>
      ) : (
        <ul className="grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">{children}</ul>
      )}
    </section>
  )
}

function InvoiceItem({
  item,
  blocked,
  onOpenInvoice,
}: {
  item: PendingInvoice
  blocked: boolean
  onOpenInvoice: (id: string) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const canInvoice = useCan('compliance.invoice')
  const issue = useIssueInvoice()
  const retry = useRetryInvoice()
  const busy = issue.isPending || retry.isPending
  async function run() {
    try {
      const result = item.invoice_id
        ? await retry.mutateAsync(item.invoice_id)
        : await issue.mutateAsync({ reservation_id: item.reservation_id! })
      toast.success(t('pending.invoiceDone', { number: result.number, status: t(`invoiceStatus.${result.status}`) }))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }
  return (
    <Row
      actions={
        <>
          {item.invoice_id && (
            <Button size="sm" variant="ghost" onClick={() => onOpenInvoice(item.invoice_id!)}>
              {t('pending.view')}
            </Button>
          )}
          {canInvoice && (item.status === 'not_issued' || item.invoice_id) && (
            <Button size="sm" loading={busy} disabled={blocked} title={blocked ? t('pending.blocked') : undefined} onClick={() => void run()}>
              {!busy && (item.status === 'not_issued' ? <ReceiptText aria-hidden /> : <RotateCcw aria-hidden />)}
              {t(item.status === 'not_issued' ? 'pending.issue' : 'pending.retry')}
            </Button>
          )}
        </>
      }
    >
      <p className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="font-semibold text-fg">{item.guest_name}</span>
        <InvoiceStatusBadge status={item.status} />
        {item.number && <span className="num text-muted">{item.number}</span>}
      </p>
      <p className="text-xs text-muted">
        {item.reservation_id && (
          <Link to={`/app/reservations/${item.reservation_id}`} className="num font-semibold text-accent-ink hover:underline">
            {item.reservation_code}
          </Link>
        )}
        {item.checkout_date && ` · ${t('pending.departed', { date: formatDate(item.checkout_date, undefined, lang) })}`}
        {' · '}
        <MoneyText value={item.total} />
      </p>
      {item.error && <p className="text-xs text-danger-ink">{item.error}</p>}
    </Row>
  )
}

function TraItem({ item }: { item: PendingTra }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const canTra = useCan('compliance.tra')
  const register = useRegisterTra()
  const noOccupants = item.missing_fields.includes('occupants')
  return (
    <Row
      actions={
        <>
          {item.guest_id && item.missing_fields.length > 0 && !noOccupants && (
            <Button asChild size="sm" variant="ghost">
              <Link to={`/app/guests/${item.guest_id}`}>
                <UserPen aria-hidden />
                {t('missing.fix')}
              </Link>
            </Button>
          )}
          {noOccupants && (
            <Button asChild size="sm" variant="ghost">
              <Link to={`/app/reservations/${item.reservation_id}?tab=guests`}>
                <UserPlus aria-hidden />
                {t('pending.addGuests')}
              </Link>
            </Button>
          )}
          {item.registration_id ? (
            <RetryTraButton registration={{ id: item.registration_id, status: item.status as 'pending' | 'error' }} />
          ) : (
            canTra &&
            !noOccupants && (
              <Button
                size="sm"
                loading={register.isPending}
                onClick={async () => {
                  try {
                    const rows = await register.mutateAsync(item.stay_id)
                    const done = rows.filter((row) => row.status === 'registered').length
                    toast.success(t('pending.traDone', { count: done, total: rows.length }))
                  } catch (error) {
                    toast.error(errorMessage(error, t))
                  }
                }}
              >
                {t('pending.register')}
              </Button>
            )
          )}
        </>
      }
    >
      <p className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="font-semibold text-fg">{item.guest_name || t('pending.unknownGuest')}</span>
        <TraStatusBadge status={item.status} />
      </p>
      <p className="text-xs text-muted">
        <Link to={`/app/reservations/${item.reservation_id}`} className="num font-semibold text-accent-ink hover:underline">
          {item.reservation_code}
        </Link>
        {item.room && ` · ${t('pending.room', { room: item.room })}`}
        {` · ${t('pending.arrived', { date: formatDate(item.checkin_date, undefined, lang) })}`}
      </p>
      {noOccupants ? (
        <p className="text-xs text-warning-ink">{t('pending.noOccupants')}</p>
      ) : (
        <MissingFields fields={item.missing_fields} scope="tra" />
      )}
      {item.error && item.missing_fields.length === 0 && <p className="text-xs text-danger-ink">{item.error}</p>}
    </Row>
  )
}

/** Tab "Pendientes": everything the law still expects from the hotel, each with the action that settles it. */
export function PendingTab({
  pending,
  sireMode,
  onOpenInvoice,
  onOpenReport,
}: {
  pending: PendingSummary
  sireMode: IntegrationMode
  onOpenInvoice: (id: string) => void
  onOpenReport: (id: string) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const canSire = useCan('compliance.sire')
  const files = useSireDownload()
  const generate = useGenerateSire()
  const [submitting, setSubmitting] = useState<PendingSummary['sire']['reports'][number] | null>(null)
  const unreported = pending.sire.unreported_days

  if (pending.counts.total === 0 && pending.resolution.status === 'ok') {
    return (
      <div className="grid gap-4">
        <EmptyState icon={CircleCheck} title={t('pending.allClear')} description={t('pending.allClearHint')} />
        <ResolutionHealthCard health={pending.resolution} className="mx-auto w-full max-w-xl" />
      </div>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <div className="grid gap-6">
        <Group
          title={t('pending.invoices')}
          count={pending.invoices.count}
          shown={pending.invoices.items.length}
          empty={t('pending.invoicesClear')}
        >
          {pending.invoices.items.map((item) => (
            <InvoiceItem
              key={item.invoice_id ?? item.reservation_id}
              item={item}
              blocked={pending.resolution.status === 'missing' || pending.resolution.status === 'critical'}
              onOpenInvoice={onOpenInvoice}
            />
          ))}
        </Group>

        <Group title={t('pending.tra')} count={pending.tra.count} shown={pending.tra.items.length} empty={t('pending.traClear')}>
          {pending.tra.items.map((item) => (
            <TraItem key={item.registration_id ?? item.stay_id} item={item} />
          ))}
        </Group>

        <Group title={t('pending.sire')} count={pending.sire.count} empty={t('pending.sireClear')}>
          {pending.sire.reports.map((report) => (
            <Row
              key={report.report_id}
              actions={
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={files.busy === report.report_id}
                    onClick={() =>
                      void files.download({ id: report.report_id, file_name: `SIRE-${report.period_start}-${report.period_end}.txt` })
                    }
                  >
                    {files.busy !== report.report_id && <Download aria-hidden />}
                    {t('sire.download')}
                  </Button>
                  {canSire && (
                    <Button size="sm" variant="primary" onClick={() => setSubmitting(report)}>
                      <Upload aria-hidden />
                      {t('sire.markSubmitted')}
                    </Button>
                  )}
                </>
              }
            >
              <button
                type="button"
                onClick={() => onOpenReport(report.report_id)}
                className="w-fit text-left text-[13px] font-semibold text-fg hover:underline"
              >
                {t('pending.sireFile', { period: formatDateRange(report.period_start, report.period_end, lang) })}
              </button>
              <p className="text-xs text-muted">
                {t('sire.counts', { records: report.records_count, missing: report.missing_count })}
              </p>
            </Row>
          ))}
          {unreported.length > 0 && (
            <Row
              actions={
                canSire && (
                  <Button
                    size="sm"
                    variant="primary"
                    loading={generate.isPending}
                    onClick={async () => {
                      try {
                        const report = await generate.mutateAsync({ start: unreported[0]!, end: unreported.at(-1)! })
                        toast.success(t('sire.generated', { records: report.records_count, missing: report.missing.length }))
                        onOpenReport(report.id)
                      } catch (error) {
                        toast.error(errorMessage(error, t))
                      }
                    }}
                  >
                    {!generate.isPending && <FileSpreadsheet aria-hidden />}
                    {t('sire.generate')}
                  </Button>
                )
              }
            >
              <p className="text-[13px] font-semibold text-fg">{t('pending.unreported', { count: unreported.length })}</p>
              <p className="num text-xs text-muted">
                {unreported.map((day) => formatDate(day, 'd MMM', lang)).join(' · ')}
              </p>
            </Row>
          )}
        </Group>
        {pending.sire.missing.length > 0 && (
          <section className="grid gap-2">
            <SectionTitle title={t('pending.sireMissing')} count={pending.sire.missing.length} />
            <MissingList items={pending.sire.missing} />
          </section>
        )}
      </div>
      <aside className="grid gap-3 lg:sticky lg:top-4">
        <ResolutionHealthCard health={pending.resolution} />
        <p className="px-1 text-xs text-muted">{t('pending.automations')}</p>
      </aside>
      <MarkSubmittedDialog
        report={submitting ? { id: submitting.report_id, period_start: submitting.period_start, period_end: submitting.period_end } : null}
        mode={sireMode}
        onOpenChange={(open) => !open && setSubmitting(null)}
      />
    </div>
  )
}
