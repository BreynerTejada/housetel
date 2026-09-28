import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronLeft, ChevronRight, MoonStar } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ME_QUERY_KEY, useActiveProperty } from '@/lib/auth'
import { formatDate, formatPercent, normalizeLang, type Lang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  bookingKeys,
  frontdeskKeys,
  getNightAuditPreview,
  getNightAuditReports,
  runNightAudit,
  type NightAuditReport,
  type NightAuditStatus,
  type NightAuditSummary,
} from '../api'
import { shortDay } from '../lib/labels'

const STATUS_TONE: Record<NightAuditStatus, BadgeTone> = { completed: 'success', partial: 'warning', running: 'info' }

function longDay(value: string, lang: Lang): string {
  return formatDate(value, lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", lang)
}

/**
 * `/app/night-audit` (plan C1): the day that is open, what closing it will do (the real audit run in a
 * transaction that is rolled back), the button that closes it, and the closing reports of past days.
 * Every night the automation `frontdesk.night_audit` does the same at 02:00.
 */
export default function NightAuditPage() {
  const { t } = useTranslation('frontdesk')
  const canRun = useCan('frontdesk.night_audit')
  return (
    <div className="mx-auto grid max-w-5xl gap-6">
      <PageHeader title={t('nav.nightAudit')} description={t('audit.description')} />
      {canRun ? (
        <CloseDay />
      ) : (
        <p className="rounded-lg border border-border bg-surface-2/60 px-4 py-3 text-[13px] text-muted">{t('audit.noPermission')}</p>
      )}
      <History />
    </div>
  )
}

function CloseDay() {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const queryClient = useQueryClient()
  const preview = useQuery({ queryKey: frontdeskKeys.auditPreview(), queryFn: getNightAuditPreview, staleTime: 0 })
  const [confirming, setConfirming] = useState(false)

  async function run(businessDate: string, nextDate: string) {
    const report = await runNightAudit(businessDate)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
      queryClient.invalidateQueries({ queryKey: frontdeskKeys.all }),
      queryClient.invalidateQueries({ queryKey: bookingKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['finance'] }),
    ])
    toast.success(t(report.status === 'partial' ? 'audit.donePartial' : 'audit.done', { date: shortDay(businessDate, lang), next: shortDay(nextDate, lang) }))
  }

  return (
    <section aria-labelledby={titleId} className="rounded-xl border border-border bg-surface shadow-xs">
      <header className="flex flex-col gap-4 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id={titleId} className="eyebrow">
            {t('audit.closeTitle')}
          </h2>
          {preview.data && (
            <>
              <p className="mt-1 text-[22px] leading-7 font-bold tracking-[-0.02em]">{longDay(preview.data.business_date, lang)}</p>
              <p className={cn('text-[13px]', preview.data.due ? 'font-semibold text-warning-ink' : 'text-muted')}>
                {preview.data.reason === 'audit_ahead'
                  ? t('audit.ahead', { today: shortDay(preview.data.calendar_date, lang) })
                  : preview.data.due
                    ? t('audit.due', { today: shortDay(preview.data.calendar_date, lang) })
                    : t('audit.early')}
              </p>
            </>
          )}
        </div>
        <Button variant="primary" disabled={!preview.data?.can_run} onClick={() => setConfirming(true)}>
          <MoonStar aria-hidden />
          {t('audit.run')}
        </Button>
      </header>
      <div className="px-5 py-5">
        {preview.isError ? (
          <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
        ) : !preview.data ? (
          <LoadingState variant="rows" rows={3} />
        ) : preview.data.summary ? (
          <SummaryView summary={preview.data.summary} mode="preview" />
        ) : (
          <p className="text-[13px] text-muted">{t('audit.nothingYet')}</p>
        )}
      </div>
      {preview.data && (
        <ConfirmDialog
          open={confirming}
          onOpenChange={setConfirming}
          title={t('audit.confirmTitle', { date: shortDay(preview.data.business_date, lang) })}
          description={t('audit.confirmHint', { next: longDay(preview.data.next_business_date, lang) })}
          confirmLabel={t('audit.run')}
          onConfirm={() => run(preview.data!.business_date, preview.data!.next_business_date)}
        />
      )}
    </section>
  )
}

/** What the audit posts, marks and alerts, and the figures of the day (preview or closed report). */
function SummaryView({ summary, mode }: { summary: NightAuditSummary; mode: 'preview' | 'report' }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const currency = property?.currency || 'COP'
  const figures = summary.figures
  return (
    <div className="grid gap-5">
      <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
        <Block label={t(mode === 'preview' ? 'audit.nightsToPost' : 'audit.nightsPosted')}>
          <p className="text-[20px] font-semibold">{t('audit.nights', { count: summary.room_charges.nights })}</p>
          <MoneyText value={summary.room_charges.total} currency={currency} className="text-[13px] text-muted" />
        </Block>
        <Block label={t('audit.noShows')}>
          <p className="text-[20px] font-semibold">{summary.no_shows.length}</p>
          {Number(summary.no_show_fees) > 0 && (
            <p className="text-[13px] text-muted">
              {t('audit.fees')} <MoneyText value={summary.no_show_fees} currency={currency} />
            </p>
          )}
        </Block>
        <Block label={t('audit.occupancy')}>
          <p className="text-[20px] font-semibold">{formatPercent(figures.occupancy_pct, 1, lang)}</p>
          <p className="text-[13px] text-muted">{t('today.roomsOf', { done: figures.rooms_occupied, total: figures.rooms_available })}</p>
        </Block>
      </div>

      {summary.no_shows.length > 0 && (
        <ListSection title={t(mode === 'preview' ? 'audit.noShowsToMark' : 'audit.noShowsMarked')}>
          {summary.no_shows.map((item) => (
            <Row key={item.reservation_id} code={item.code} reservationId={item.reservation_id} name={item.guest_name}>
              <MoneyText value={item.fee} currency={currency} className="text-[13px] font-semibold" />
            </Row>
          ))}
        </ListSection>
      )}
      {summary.overdue_departures.length > 0 && (
        <ListSection title={t('audit.overdue')}>
          {summary.overdue_departures.map((item) => (
            <Row key={item.stay_id} code={item.code} reservationId={item.reservation_id} name={item.guest_name}>
              <span className="text-[13px] text-danger-ink">{t('chips.overdue', { date: shortDay(item.checkout, lang) })}</span>
            </Row>
          ))}
        </ListSection>
      )}
      {summary.pending_tentative.length > 0 && (
        <ListSection title={t('audit.tentative')}>
          {summary.pending_tentative.map((item) => (
            <Row key={item.reservation_id} code={item.code} reservationId={item.reservation_id} name={item.guest_name}>
              <span className="text-[13px] text-muted">{shortDay(item.checkin, lang)}</span>
            </Row>
          ))}
        </ListSection>
      )}
      {summary.errors.length > 0 && (
        <ListSection title={t('audit.errors')}>
          {summary.errors.map((item, index) => (
            <Row key={`${item.reservation_id}-${index}`} code={item.code} reservationId={item.reservation_id} name={item.error} tone="danger" />
          ))}
        </ListSection>
      )}

      <dl className="grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-5">
        <Figure label={t('audit.roomRevenue')} value={<MoneyText value={figures.room_revenue} currency={currency} />} />
        <Figure label={t('audit.otherRevenue')} value={<MoneyText value={figures.other_revenue} currency={currency} />} />
        <Figure label="ADR" value={<MoneyText value={figures.adr} currency={currency} />} />
        <Figure label="RevPAR" value={<MoneyText value={figures.revpar} currency={currency} />} />
        <Figure label={t('audit.collected')} value={<MoneyText value={figures.collected} currency={currency} />} />
      </dl>
    </div>
  )
}

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 bg-surface p-4">
      <p className="text-[13px] font-semibold text-muted">{label}</p>
      {children}
    </div>
  )
}

function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="num mt-0.5 font-semibold text-fg">{value}</dd>
    </div>
  )
}

function ListSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2">
      <h3 className="eyebrow">{title}</h3>
      <ul className="divide-y divide-border rounded-lg border border-border">{children}</ul>
    </section>
  )
}

function Row({
  code,
  reservationId,
  name,
  tone,
  children,
}: {
  code: string
  reservationId: string
  name: string
  tone?: 'danger'
  children?: ReactNode
}) {
  const labelId = useId()
  return (
    <li aria-labelledby={labelId} className="flex items-center justify-between gap-3 px-3 py-2">
      <p className="min-w-0 text-[13px]">
        <Link id={labelId} to={`/app/reservations/${reservationId}`} className="num font-semibold text-fg hover:text-accent-ink hover:underline">
          {code}
        </Link>{' '}
        <span className={tone === 'danger' ? 'text-danger-ink' : 'text-muted'}>{name}</span>
      </p>
      {children}
    </li>
  )
}

function History() {
  const { t } = useTranslation('frontdesk')
  const titleId = useId()
  const [page, setPage] = useState(1)
  const reports = useQuery({ queryKey: frontdeskKeys.auditReports(page), queryFn: () => getNightAuditReports(page) })
  const count = reports.data?.count ?? 0

  return (
    <section aria-labelledby={titleId} className="grid gap-3">
      <h2 id={titleId} className="text-[15px] font-bold">
        {t('audit.history')}
      </h2>
      {reports.isError ? (
        <ErrorState error={reports.error} onRetry={() => reports.refetch()} />
      ) : !reports.data ? (
        <LoadingState variant="rows" rows={4} />
      ) : reports.data.results.length === 0 ? (
        <EmptyState icon={MoonStar} title={t('audit.noReports')} className="rounded-xl border border-border bg-surface" />
      ) : (
        <>
          <ul className="grid gap-2">
            {reports.data.results.map((report) => (
              <ReportRow key={report.id} report={report} />
            ))}
          </ul>
          {count > reports.data.results.length && (
            <div className="flex items-center justify-end gap-2">
              <Button size="icon-sm" aria-label={t('common:table.previous')} disabled={!reports.data.previous} onClick={() => setPage((value) => value - 1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button size="icon-sm" aria-label={t('common:table.next')} disabled={!reports.data.next} onClick={() => setPage((value) => value + 1)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function ReportRow({ report }: { report: NightAuditReport }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const dateId = useId()
  const detailId = useId()
  const [open, setOpen] = useState(false)
  const summary = report.summary
  const figures = summary?.figures

  return (
    <li aria-labelledby={dateId} className="rounded-xl border border-border bg-surface shadow-xs">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <p id={dateId} className="num min-w-32 font-semibold text-fg">
          {formatDate(report.business_date, lang === 'en' ? 'EEE, MMM d' : 'EEE d MMM', lang)}
        </p>
        <Badge tone={STATUS_TONE[report.status]}>{t(`audit.status.${report.status}`)}</Badge>
        {figures && (
          <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
            <div className="flex gap-1.5">
              <dt className="text-muted">{t('audit.occupancy')}</dt>
              <dd className="num font-semibold">{formatPercent(figures.occupancy_pct, 1, lang)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-muted">{t('audit.revenue')}</dt>
              <dd>
                <MoneyText value={figures.revenue} className="font-semibold" />
              </dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-muted">{t('audit.noShows')}</dt>
              <dd className="num font-semibold">{summary.no_shows.length}</dd>
            </div>
          </dl>
        )}
        <Button variant="ghost" size="sm" className="ml-auto" aria-expanded={open} aria-controls={detailId} onClick={() => setOpen((value) => !value)}>
          {t('audit.details')}
          <ChevronDown aria-hidden className={open ? 'rotate-180' : undefined} />
        </Button>
      </div>
      {open && (
        <div id={detailId} className="border-t border-border px-4 py-4">
          <p className="mb-3 text-xs text-muted">
            {report.triggered_by ? t('audit.ranBy', { name: report.triggered_by.full_name }) : t('audit.ranAutomatically')}
            {report.finished_at && ` · ${formatDate(report.finished_at, lang === 'en' ? 'MMM d, HH:mm' : 'd MMM, HH:mm', lang)}`}
          </p>
          {summary && <SummaryView summary={summary} mode="report" />}
        </div>
      )}
    </li>
  )
}
