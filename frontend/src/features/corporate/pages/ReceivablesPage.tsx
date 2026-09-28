import { ArrowRight, Download, HandCoins } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { saveBlob } from '@/features/finance/download'
import { moneyLabel, toCents } from '@/features/finance/money'
import { AGING_KEYS, downloadReceivablesCsv, useReceivables, type Receivables, type ReceivablesRow } from '../api'
import { AgingRibbon } from '../components/AgingRibbon'
import { AGING_FILL } from '../lib/aging'

/** `/app/receivables`: what the companies owe this hotel, by age, and who is late. */
export default function ReceivablesPage() {
  const { t } = useTranslation('corporate')
  const receivables = useReceivables()
  const [exporting, setExporting] = useState(false)

  async function exportCsv() {
    setExporting(true)
    try {
      saveBlob(await downloadReceivablesCsv(), `cartera-${receivables.data?.as_of ?? 'hoy'}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-7xl grid-cols-1">
      <PageHeader
        title={t('receivables.title')}
        description={t('receivables.description')}
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/app/companies">{t('receivables.companies')}</Link>
            </Button>
            <Button variant="secondary" loading={exporting} disabled={!receivables.data} onClick={() => void exportCsv()}>
              {!exporting && <Download aria-hidden />}
              {t('receivables.export')}
            </Button>
          </>
        }
      />
      {receivables.isPending ? (
        <LoadingState variant="rows" rows={6} />
      ) : receivables.isError ? (
        <ErrorState error={receivables.error} onRetry={() => void receivables.refetch()} />
      ) : (
        <ReceivablesView data={receivables.data} />
      )}
    </div>
  )
}

function ReceivablesView({ data }: { data: Receivables }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  const currency = data.currency
  const { totals } = data
  const hasBalance = toCents(totals.balance) > 0

  if (data.companies.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface shadow-xs">
        <EmptyState
          icon={HandCoins}
          title={t('receivables.empty')}
          description={t('receivables.emptyHint')}
          action={
            <Button asChild variant="secondary">
              <Link to="/app/companies">{t('receivables.companies')}</Link>
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6">
      <section aria-label={t('receivables.summary')} className="@container grid min-w-0 grid-cols-1 gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow">{t('receivables.total')}</p>
            <p className="num mt-1 text-[34px] leading-10 font-semibold tracking-[-0.035em] text-fg">
              <MoneyText value={totals.balance} currency={currency} />
            </p>
            <p className="mt-1 text-[13px] text-muted">
              {t('receivables.asOf', { date: formatDate(data.as_of, undefined, lang), count: totals.companies })}
            </p>
          </div>
          <dl className="grid w-full grid-cols-2 gap-x-6 gap-y-2 sm:w-auto sm:grid-cols-3 sm:text-right">
            <div>
              <dt className="text-xs text-muted">{t('receivables.overdue')}</dt>
              <dd className={cn('text-sm font-semibold', toCents(totals.overdue) > 0 && 'text-danger-ink')}>
                <MoneyText value={totals.overdue} currency={currency} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">{t('receivables.unapplied')}</dt>
              <dd className="text-sm font-semibold">
                <MoneyText value={totals.unapplied} currency={currency} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">{t('receivables.inProgress')}</dt>
              <dd className="text-sm font-semibold">
                <MoneyText value={totals.in_progress} currency={currency} />
              </dd>
            </div>
          </dl>
        </div>
        {hasBalance && <AgingRibbon aging={data.aging} currency={currency} />}
      </section>

      <section aria-labelledby="receivables-companies" className="grid min-w-0 grid-cols-1 gap-3">
        <h2 id="receivables-companies" className="text-[15px] font-bold">
          {t('receivables.byCompany')}
        </h2>
        <CompanyCards rows={data.companies} currency={currency} />
        <CompanyTable rows={data.companies} currency={currency} />
      </section>
    </div>
  )
}

/** Phones: one card per company with its mini ribbon. */
function CompanyCards({ rows, currency }: { rows: ReceivablesRow[]; currency: string }) {
  const { t } = useTranslation('corporate')
  return (
    <ul className="grid grid-cols-1 gap-3 md:hidden">
      {rows.map((row) => (
        <li key={row.company.id}>
          <Link
            to={`/app/companies/${row.company.id}`}
            className="grid grid-cols-1 gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-semibold text-fg">{row.company.legal_name}</p>
                <p className="num text-xs text-muted">NIT {row.company.nit_display}</p>
              </div>
              <div className="grid justify-items-end">
                <MoneyText value={row.balance} currency={currency} className="font-semibold" />
                {toCents(row.overdue) > 0 && (
                  <span className="text-xs text-danger-ink">{t('list.overdue', { amount: moneyLabel(row.overdue, currency) })}</span>
                )}
              </div>
            </div>
            {toCents(row.balance) > 0 && <AgingRibbon aging={row.aging} currency={currency} variant="mini" />}
            <RowBadges row={row} currency={currency} />
          </Link>
        </li>
      ))}
    </ul>
  )
}

function RowBadges({ row, currency }: { row: ReceivablesRow; currency: string }) {
  const { t } = useTranslation('corporate')
  const badges = [
    toCents(row.unapplied) > 0 && (
      <Badge key="favor" tone="info">
        {t('statement.unappliedBadge', { amount: moneyLabel(row.unapplied, currency) })}
      </Badge>
    ),
    toCents(row.in_progress) > 0 && (
      <Badge key="progress" tone="neutral">
        {t('list.inProgress', { amount: moneyLabel(row.in_progress, currency) })}
      </Badge>
    ),
    row.oldest_days > 0 && (
      <span key="oldest" className="text-xs text-muted">
        {t('receivables.oldest', { count: row.oldest_days })}
      </span>
    ),
  ].filter(Boolean)
  if (!badges.length) return null
  return <div className="flex flex-wrap items-center gap-1.5">{badges}</div>
}

/** Tablets and up: the classic aging table (one column per band). */
function CompanyTable({ rows, currency }: { rows: ReceivablesRow[]; currency: string }) {
  const { t } = useTranslation('corporate')
  const navigate = useNavigate()
  return (
    <div className="hidden overflow-hidden rounded-xl border border-border bg-surface shadow-xs md:block">
      <Table aria-label={t('receivables.byCompany')}>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>{t('list.columns.company')}</TableHead>
            {AGING_KEYS.map((key) => (
              <TableHead key={key} className="text-right">
                <span className="inline-flex items-center justify-end gap-1.5">
                  <span aria-hidden className={cn('size-2 rounded-[2px]', AGING_FILL[key])} />
                  {t(`aging.short.${key}`)}
                </span>
              </TableHead>
            ))}
            <TableHead className="text-right">{t('receivables.balance')}</TableHead>
            <TableHead className="hidden text-right lg:table-cell">{t('receivables.overdue')}</TableHead>
            <TableHead className="w-8">
              <span className="sr-only">{t('receivables.open')}</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={row.company.id}
              tabIndex={0}
              onClick={() => navigate(`/app/companies/${row.company.id}`)}
              onKeyDown={(event) => event.key === 'Enter' && navigate(`/app/companies/${row.company.id}`)}
              className="cursor-pointer focus-visible:bg-surface-2 focus-visible:outline-none"
            >
              <TableCell className="max-w-0 min-w-52">
                <p className="truncate font-semibold text-fg">{row.company.legal_name}</p>
                <div className="mt-1">
                  <RowBadges row={row} currency={currency} />
                </div>
              </TableCell>
              {AGING_KEYS.map((key) => (
                <TableCell key={key} className={cn('num text-right text-[13px]', toCents(row.aging[key]) === 0 && 'text-subtle')}>
                  <MoneyText value={row.aging[key]} currency={currency} />
                </TableCell>
              ))}
              <TableCell className="text-right font-semibold">
                <MoneyText value={row.balance} currency={currency} />
              </TableCell>
              <TableCell className={cn('hidden text-right lg:table-cell', toCents(row.overdue) > 0 ? 'text-danger-ink' : 'text-subtle')}>
                <MoneyText value={row.overdue} currency={currency} />
              </TableCell>
              <TableCell className="px-1 text-muted">
                <ArrowRight aria-hidden className="size-4" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
