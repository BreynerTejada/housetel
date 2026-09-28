import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ReportColumn, ReportTableData, TableRow as Row } from '../api'
import { cellText, isNumericColumn, sortValue } from '../lib/format'

const PAGE_SIZE = 50
const SEARCH_FROM = 12
/** Free-text columns that may wrap; every other cell stays on one line and the table scrolls sideways. */
const WRAPPING = new Set(['reason', 'occupant', 'arrival_today'])

type Sort = { key: string; dir: 'asc' | 'desc' } | null

/**
 * A report table as the API sends it: typed columns (money, dates, statuses…), the rows and a totals row.
 * Click a header to sort; tables with many rows get a search box and pages of 50.
 */
export function ReportTable({ table, currency, loading }: { table: ReportTableData; currency: string; loading: boolean }) {
  const { t, i18n } = useTranslation('reports')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const [sort, setSort] = useState<Sort>(null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const ctx = useMemo(
    () => ({ currency, lang, yes: t('table.yes'), no: t('table.no'), unknown: t('table.unknown') }),
    [currency, lang, t],
  )

  const rows = useMemo(() => {
    let result = table.rows
    const needle = query.trim().toLowerCase()
    if (needle) {
      result = result.filter((row) =>
        table.columns.some((column) => cellText(row[column.key], column, ctx).toLowerCase().includes(needle)),
      )
    }
    if (sort) {
      const column = table.columns.find((item) => item.key === sort.key)
      if (column) {
        const factor = sort.dir === 'asc' ? 1 : -1
        result = [...result].sort((a, b) => {
          const left = sortValue(a[column.key], column, lang)
          const right = sortValue(b[column.key], column, lang)
          if (typeof left === 'number' && typeof right === 'number') return (left - right) * factor
          return String(left).localeCompare(String(right), lang) * factor
        })
      }
    }
    return result
  }, [table, query, sort, ctx, lang])

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const current = Math.min(page, pages - 1)
  const visible = rows.length > PAGE_SIZE ? rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE) : rows
  const searchable = table.rows.length > SEARCH_FROM

  function toggleSort(key: string) {
    setPage(0)
    setSort((previous) => {
      if (!previous || previous.key !== key) return { key, dir: 'asc' }
      if (previous.dir === 'asc') return { key, dir: 'desc' }
      return null
    })
  }

  return (
    <section aria-labelledby={titleId} className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-baseline gap-2">
          <h2 id={titleId} className="text-[15px] font-bold text-fg">
            {table.title}
          </h2>
          <span className="num text-xs text-muted">{t('table.rows', { count: rows.length })}</span>
        </div>
        {searchable && (
          <div className="relative w-full sm:w-64">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-subtle" />
            <Input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setPage(0)
              }}
              placeholder={t('table.search')}
              aria-label={t('table.search')}
              className="h-8 pl-8"
            />
          </div>
        )}
      </header>

      <Table aria-labelledby={titleId} aria-busy={loading || undefined} className={cn('transition-opacity', loading && 'opacity-60')}>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {table.columns.map((column) => {
              const active = sort?.key === column.key ? sort.dir : null
              const Icon = active === 'asc' ? ArrowUp : active === 'desc' ? ArrowDown : ArrowUpDown
              return (
                <TableHead
                  key={column.key}
                  scope="col"
                  aria-sort={active === 'asc' ? 'ascending' : active === 'desc' ? 'descending' : undefined}
                  className={cn(isNumericColumn(column) && 'text-right')}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    aria-label={t('table.sortBy', { column: column.label })}
                    className={cn(
                      '-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                      isNumericColumn(column) && 'flex-row-reverse',
                      active && 'text-fg',
                    )}
                  >
                    {column.label}
                    <Icon aria-hidden className={cn('size-3.5', !active && 'opacity-40')} />
                  </button>
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={table.columns.length} className="px-6 py-12 text-center text-sm text-muted">
                {t('table.empty')}
              </TableCell>
            </TableRow>
          ) : (
            visible.map((row, index) => (
              <TableRow key={`${row.reservation_id ?? ''}-${index}`}>
                {table.columns.map((column) => (
                  <TableCell
                    key={column.key}
                    className={cn(
                      'py-2',
                      WRAPPING.has(column.key) ? 'max-w-[18rem] min-w-[12rem] whitespace-normal' : 'whitespace-nowrap',
                      isNumericColumn(column) && 'num text-right',
                    )}
                  >
                    <Cell row={row} column={column} ctx={ctx} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
        {table.totals && visible.length > 0 && !query.trim() && (
          <TableFooter>
            <TableRow className="hover:bg-transparent">
              {table.columns.map((column, index) => {
                const value = table.totals?.[column.key]
                return (
                  <TableCell key={column.key} className={cn('py-2.5 font-bold', isNumericColumn(column) && 'num text-right whitespace-nowrap')}>
                    {index === 0 && (value === null || value === undefined || value === '') && !hasTotalsLabel(table)
                      ? t('table.total')
                      : value === null || value === undefined
                        ? ''
                        : column.type === 'text'
                          ? String(value)
                          : cellText(value, column, ctx)}
                  </TableCell>
                )
              })}
            </TableRow>
          </TableFooter>
        )}
      </Table>

      {rows.length > PAGE_SIZE && (
        <footer className="flex items-center justify-end gap-2 border-t border-border px-3 py-2 text-[13px] text-muted">
          <span className="num">{`${current * PAGE_SIZE + 1}–${Math.min((current + 1) * PAGE_SIZE, rows.length)} / ${rows.length}`}</span>
          <Button variant="secondary" size="icon-sm" aria-label={t('table.previous')} disabled={current === 0} onClick={() => setPage(current - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <Button variant="secondary" size="icon-sm" aria-label={t('table.next')} disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
            <ChevronRight aria-hidden />
          </Button>
        </footer>
      )}
    </section>
  )
}

/** Whether the backend already labelled the totals row in a text column ("Total" under the booking code). */
function hasTotalsLabel(table: ReportTableData): boolean {
  return table.columns.some((column) => column.type === 'text' && typeof table.totals?.[column.key] === 'string' && table.totals[column.key] !== '')
}

function Cell({ row, column, ctx }: { row: Row; column: ReportColumn; ctx: { currency: string; lang: Lang; yes: string; no: string; unknown: string } }) {
  const { t } = useTranslation('reports')
  const value = row[column.key]
  if (value === null || value === undefined || value === '') return <span className="text-subtle">—</span>

  if (column.link === 'reservation' && typeof row.reservation_id === 'string' && row.reservation_id) {
    return (
      <Link
        to={`/app/reservations/${row.reservation_id}`}
        aria-label={t('table.openReservation', { code: String(value) })}
        className="num font-semibold text-accent-ink underline-offset-4 hover:underline"
      >
        {String(value)}
      </Link>
    )
  }
  if (column.type === 'status' && column.status_kind) {
    return <StatusBadge kind={column.status_kind} status={String(value)} />
  }
  if (column.type === 'boolean') {
    if (column.key === 'vip') return value ? <Badge tone="accent">VIP</Badge> : null
    return value ? <span className="font-semibold text-fg">{ctx.yes}</span> : <span className="text-subtle">{ctx.no}</span>
  }
  const text = cellText(value, column, ctx)
  if (column.type === 'money' && Number(value) < 0) return <span className="text-danger-ink">{text}</span>
  if (column.type === 'date' || column.type === 'datetime') return <span className="num whitespace-nowrap">{text}</span>
  return <>{text}</>
}
