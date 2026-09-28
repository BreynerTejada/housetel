import type { ColumnDef } from '@tanstack/react-table'
import { subDays } from 'date-fns'
import { Download, FileSpreadsheet, PlaneLanding, PlaneTakeoff, Upload, UserPen } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DataTable } from '@/components/DataTable'
import { DateRangePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { DateRangeValue } from '@/lib/date-ranges'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import {
  useGenerateSire,
  useMarkSireSubmitted,
  useSireReport,
  type IntegrationMode,
  type SireMissing,
  type SireReport,
} from '../api'
import { useSireDownload } from '../hooks'
import { buildSireDays } from '../lib/sire'
import { MissingFields, SireStatusBadge, SimulatedBadge } from './common'
import { SireDayStrip } from './SireDayStrip'

/** "Marcar como reportado": after uploading the file in the SIRE portal (the receipt code is optional). */
export function MarkSubmittedDialog({
  report,
  mode,
  onOpenChange,
}: {
  report: Pick<SireReport, 'id' | 'period_start' | 'period_end'> | null
  mode: IntegrationMode
  onOpenChange: (open: boolean) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const ackId = useId()
  const [ack, setAck] = useState('')
  const mark = useMarkSireSubmitted()
  return (
    <ConfirmDialog
      open={Boolean(report)}
      onOpenChange={(open) => {
        if (!open) setAck('')
        onOpenChange(open)
      }}
      title={t('sire.submit.title')}
      description={
        report ? t('sire.submit.description', { period: formatDateRange(report.period_start, report.period_end, lang) }) : ''
      }
      confirmLabel={t('sire.submit.confirm')}
      onConfirm={async () => {
        if (!report) return
        const result = await mark.mutateAsync({ id: report.id, ack_code: ack.trim() })
        toast.success(result.ack_code ? t('sire.submit.doneAck', { code: result.ack_code }) : t('sire.submit.done'))
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={ackId}>{t('sire.submit.ack')}</Label>
        <Input id={ackId} name="ack_code" value={ack} onChange={(event) => setAck(event.target.value)} autoComplete="off" />
        <p className="text-xs text-muted">{t(mode === 'simulated' ? 'sire.submit.ackSimulated' : 'sire.submit.ackHint')}</p>
      </div>
    </ConfirmDialog>
  )
}

/** Foreign guests whose data is incomplete, with a way to fix it in their profile. */
export function MissingList({ items }: { items: SireMissing[] }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  if (items.length === 0) return null
  return (
    <ul className="grid divide-y divide-border rounded-lg border border-warning/40">
      {items.map((item) => (
        <li key={`${item.stay_id}-${item.guest_id}-${item.movement}`} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2.5">
          <div className="grid gap-1">
            <p className="text-[13px] font-semibold text-fg">
              {item.guest_name}
              <span className="ml-2 font-normal text-muted">
                {t(`sire.movement.${item.movement}`)} · {formatDate(item.movement_date, undefined, lang)} ·{' '}
                <Link to={`/app/reservations/${item.reservation_id}`} className="num text-accent-ink hover:underline">
                  {item.reservation_code}
                </Link>
              </span>
            </p>
            <MissingFields fields={item.fields} scope="sire" />
          </div>
          <Button asChild size="sm" variant="ghost">
            <Link to={`/app/guests/${item.guest_id}`}>
              <UserPen aria-hidden />
              {t('missing.fix')}
            </Link>
          </Button>
        </li>
      ))}
    </ul>
  )
}

function SireReportSheet({ reportId, mode, onOpenChange }: { reportId: string | null; mode: IntegrationMode; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const query = useSireReport(reportId)
  const files = useSireDownload()
  const canSire = useCan('compliance.sire')
  const [submitting, setSubmitting] = useState(false)
  const report = query.data
  return (
    <Sheet open={Boolean(reportId)} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(38rem,96vw)]">
        <SheetHeader>
          <p className="eyebrow">{t('sire.report')}</p>
          <SheetTitle className="num flex flex-wrap items-center gap-2">
            {report ? formatDateRange(report.period_start, report.period_end, lang) : '…'}
            {report && <SireStatusBadge status={report.status} />}
            {report && <SimulatedBadge mode={report.mode} />}
          </SheetTitle>
          <SheetDescription>
            {report ? t('sire.counts', { records: report.records_count, missing: report.missing.length }) : ''}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="grid content-start gap-5">
          {query.isPending ? (
            <LoadingState variant="rows" rows={5} className="p-0" />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : (
            <>
              {report!.ack_code && (
                <p className="rounded-lg bg-success-soft px-3 py-2 text-[13px] text-success-ink">
                  {t('sire.acknowledged', { code: report!.ack_code })}
                </p>
              )}
              {report!.missing.length > 0 && (
                <section className="grid gap-2">
                  <h3 className="eyebrow">{t('sire.missingTitle', { count: report!.missing.length })}</h3>
                  <p className="text-[13px] text-muted">{t('sire.missingHint')}</p>
                  <MissingList items={report!.missing} />
                </section>
              )}
              <section className="grid gap-2">
                <h3 className="eyebrow">{t('sire.recordsTitle', { count: report!.records.filter((r) => r.complete).length })}</h3>
                {report!.records.filter((r) => r.complete).length === 0 ? (
                  <p className="text-[13px] text-muted">{t('sire.noRecords')}</p>
                ) : (
                  <ul className="grid divide-y divide-border rounded-lg border border-border">
                    {report!.records
                      .filter((record) => record.complete)
                      .map((record) => {
                        const Icon = record.movement === 'E' ? PlaneLanding : PlaneTakeoff
                        return (
                          <li key={record.id} className="flex items-center gap-3 px-3 py-2 text-[13px]">
                            <Icon aria-hidden className="size-4 shrink-0 text-muted" />
                            <div className="min-w-0 flex-1">
                              <p className="truncate font-semibold text-fg">{record.guest_name}</p>
                              <p className="num text-xs text-muted">
                                {record.document} · {t('sire.countryCode', { code: record.nationality })}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-fg">{t(`sire.movement.${record.movement}`)}</p>
                              <p className="num text-xs text-muted">{formatDate(record.movement_date, undefined, lang)}</p>
                            </div>
                          </li>
                        )
                      })}
                  </ul>
                )}
              </section>
            </>
          )}
        </SheetBody>
        {report && (
          <SheetFooter className="flex-wrap">
            <Button onClick={() => void files.download(report)} loading={files.busy === report.id}>
              <Download aria-hidden />
              {t('sire.download')}
            </Button>
            {canSire && report.status !== 'acknowledged' && (
              <Button variant="primary" onClick={() => setSubmitting(true)}>
                <Upload aria-hidden />
                {t(report.status === 'submitted' ? 'sire.addAck' : 'sire.markSubmitted')}
              </Button>
            )}
          </SheetFooter>
        )}
        <MarkSubmittedDialog report={submitting ? (report ?? null) : null} mode={mode} onOpenChange={setSubmitting} />
      </SheetContent>
    </Sheet>
  )
}

/** Tab "SIRE": the 30-day picture, the file generator and the files already generated. */
export function SireTab({
  businessDate,
  reports,
  unreportedDays,
  mode,
  isLoading,
  error,
  onRetry,
  openReport,
  onOpenReport,
}: {
  businessDate?: string
  reports: SireReport[]
  unreportedDays: string[]
  mode: IntegrationMode
  isLoading: boolean
  error: unknown
  onRetry: () => void
  openReport: string | null
  onOpenReport: (id: string | null) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const canSire = useCan('compliance.sire')
  const generate = useGenerateSire()
  const files = useSireDownload()
  const [submitting, setSubmitting] = useState<SireReport | null>(null)
  const yesterday = toISODate(subDays(parseDate(businessDate) ?? new Date(), 1))
  const [range, setRange] = useState<DateRangeValue | null>(
    unreportedDays.length ? { from: unreportedDays[0]!, to: unreportedDays.at(-1)! } : { from: yesterday, to: yesterday },
  )
  const days = useMemo(() => buildSireDays(businessDate, reports, unreportedDays), [businessDate, reports, unreportedDays])

  const columns = useMemo<ColumnDef<SireReport>[]>(
    () => [
      {
        id: 'period',
        header: t('sire.period'),
        cell: ({ row }) => (
          <span className="num font-semibold whitespace-nowrap text-fg">
            {formatDateRange(row.original.period_start, row.original.period_end, lang)}
          </span>
        ),
      },
      { accessorKey: 'records_count', header: t('sire.records'), meta: { align: 'right' } },
      {
        accessorKey: 'missing_count',
        header: t('sire.missing'),
        meta: { align: 'right' },
        cell: ({ row }) =>
          row.original.missing_count ? (
            <span className="font-semibold text-warning-ink">{row.original.missing_count}</span>
          ) : (
            <span className="text-subtle">0</span>
          ),
      },
      { accessorKey: 'status', header: t('sire.status'), cell: ({ row }) => <SireStatusBadge status={row.original.status} /> },
      {
        accessorKey: 'generated_at',
        header: t('sire.generatedAt'),
        cell: ({ row }) => <span className="num whitespace-nowrap text-muted">{formatDate(row.original.generated_at, undefined, lang)}</span>,
      },
      {
        accessorKey: 'ack_code',
        header: t('sire.ack'),
        cell: ({ row }) => <span className="num text-xs">{row.original.ack_code || '—'}</span>,
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">{t('actionsLabel')}</span>,
        meta: { align: 'right' },
        cell: ({ row }) => (
          <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={t('sire.downloadPeriod', { period: formatDateRange(row.original.period_start, row.original.period_end, lang) })}
              loading={files.busy === row.original.id}
              onClick={() => void files.download(row.original)}
            >
              {files.busy !== row.original.id && <Download aria-hidden />}
            </Button>
            {canSire && row.original.status === 'generated' && (
              <Button size="sm" onClick={() => setSubmitting(row.original)}>
                <Upload aria-hidden />
                <span className="hidden sm:inline">{t('sire.markSubmitted')}</span>
              </Button>
            )}
          </div>
        ),
      },
    ],
    [t, lang, canSire, files],
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      <section className="grid gap-5 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="grid content-start gap-3">
          <div>
            <h2 className="text-[15px] font-bold text-fg">{t('sire.windowTitle')}</h2>
            <p className="text-[13px] text-muted">{t('sire.windowHint')}</p>
          </div>
          <SireDayStrip days={days} legend />
        </div>
        {canSire && (
          <form
            className="grid content-start gap-3 rounded-lg bg-surface-2/70 p-4"
            onSubmit={async (event) => {
              event.preventDefault()
              if (!range) return
              try {
                const report = await generate.mutateAsync({ start: range.from, end: range.to })
                toast.success(t('sire.generated', { records: report.records_count, missing: report.missing.length }))
                onOpenReport(report.id)
              } catch (err) {
                toast.error(errorMessage(err, t))
              }
            }}
          >
            <div>
              <h2 className="text-[15px] font-bold text-fg">{t('sire.generateTitle')}</h2>
              <p className="text-[13px] text-muted">{t('sire.generateHint')}</p>
            </div>
            <DateRangePicker
              value={range}
              onChange={setRange}
              today={businessDate}
              max={businessDate}
              presets={['yesterday', 'thisWeek', 'lastMonth', 'last30']}
              aria-label={t('sire.period')}
              numberOfMonths={1}
            />
            <Button type="submit" variant="primary" loading={generate.isPending} disabled={!range}>
              <FileSpreadsheet aria-hidden />
              {t('sire.generate')}
            </Button>
          </form>
        )}
      </section>

      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : (
        <DataTable
          aria-label={t('sire.title')}
          columns={columns}
          data={reports}
          isLoading={isLoading}
          getRowId={(row) => row.id}
          pageSize={10}
          onRowClick={(row) => onOpenReport(row.id)}
          empty={<EmptyState icon={FileSpreadsheet} title={t('sire.empty')} description={t('sire.emptyHint')} />}
        />
      )}
      <p className="text-xs text-muted">{t('sire.portalHint')}</p>
      <SireReportSheet reportId={openReport} mode={mode} onOpenChange={(open) => !open && onOpenReport(null)} />
      <MarkSubmittedDialog report={submitting} mode={mode} onOpenChange={(open) => !open && setSubmitting(null)} />
    </div>
  )
}
