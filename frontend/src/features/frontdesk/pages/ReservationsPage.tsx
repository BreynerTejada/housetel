import type { ColumnDef, PaginationState, SortingState, Updater } from '@tanstack/react-table'
import { Download, Plus, Star, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { DataTable } from '@/components/DataTable'
import { DateRangePicker } from '@/components/DatePicker'
import { ErrorState } from '@/components/ErrorState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { saveBlob } from '@/features/finance/download'
import { useDebouncedValue } from '@/features/guests/hooks'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  exportReservations,
  RESERVATION_SOURCES,
  RESERVATION_STATUSES,
  useReservations,
  type ReservationListItem,
} from '../api'
import { unitLabel } from '../lib/labels'
import { buildListParams, listStateSearch, parseListState, QUICK_VIEWS, type ListState, type QuickView } from '../lib/quickViews'

const ALL = '__all'

/**
 * `/app/reservations` (plan C1): every reservation of the hotel, with quick views for the day (arrivals,
 * departures, in house, unpaid, unassigned, tentative), search, filters and CSV export. The whole state lives
 * in the URL so a view can be shared or bookmarked.
 */
export default function ReservationsPage() {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? ''
  const canBook = useCan('bookings.manage')
  const state = useMemo(() => parseListState(searchParams), [searchParams])
  const params = useMemo(() => buildListParams(state, bd), [state, bd])
  const reservations = useReservations(params)
  const [text, setText] = useState(state.q)
  const search = useDebouncedValue(text, 300)
  const [exporting, setExporting] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  function update(patch: Partial<ListState>) {
    const next = { ...state, page: 1, ...patch }
    setSearchParams(listStateSearch(next), { replace: true })
  }

  // The search box writes to the URL once the user stops typing.
  useEffect(() => {
    if (search.trim() !== state.q) update({ q: search.trim() })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  // ⌘K "Buscar reserva por código" opens the list with the search box focused.
  const focusSearch = searchParams.get('focus') === 'search'
  useEffect(() => {
    if (!focusSearch) return
    containerRef.current?.querySelector<HTMLInputElement>('input[type="search"]')?.focus()
  }, [focusSearch])

  const sorting: SortingState = state.ordering
    ? [{ id: state.ordering.replace(/^-/, ''), desc: state.ordering.startsWith('-') }]
    : []

  function onSortingChange(updater: Updater<SortingState>) {
    const next = typeof updater === 'function' ? updater(sorting) : updater
    const first = next[0]
    update({ ordering: first ? `${first.desc ? '-' : ''}${first.id}` : '' })
  }

  const pagination: PaginationState = { pageIndex: state.page - 1, pageSize: state.pageSize }
  function onPaginationChange(updater: Updater<PaginationState>) {
    const next = typeof updater === 'function' ? updater(pagination) : updater
    setSearchParams(listStateSearch({ ...state, page: next.pageIndex + 1, pageSize: next.pageSize }), { replace: true })
  }

  async function exportCsv() {
    setExporting(true)
    try {
      const { page: _page, page_size: _size, ...filters } = params
      const blob = await exportReservations(filters, lang)
      saveBlob(blob, `${t('list.exportFile')}-${bd}.csv`)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setExporting(false)
    }
  }

  const columns = useMemo<ColumnDef<ReservationListItem>[]>(
    () => [
      {
        id: 'code',
        header: t('list.columns.reservation'),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="num font-semibold text-fg">{row.original.code}</p>
            <p className="truncate text-xs text-muted">
              {row.original.channel_code ? row.original.channel_code : t(`sources.${row.original.source}`)}
            </p>
          </div>
        ),
      },
      {
        id: 'guest',
        header: t('list.columns.guest'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 font-semibold text-fg">
              <span className="truncate">{row.original.booker.full_name}</span>
              {row.original.booker.is_vip && <Star role="img" aria-label={t('vip')} className="size-3.5 shrink-0 fill-warning text-warning" />}
            </p>
            {row.original.booker.email && <p className="truncate text-xs text-muted">{row.original.booker.email}</p>}
          </div>
        ),
      },
      {
        id: 'checkin_date',
        header: t('list.columns.stay'),
        cell: ({ row }) => (
          <div>
            <p className="num whitespace-nowrap text-fg">{formatDateRange(row.original.checkin_date, row.original.checkout_date, lang)}</p>
            <p className="text-xs text-muted">{t('common:date.nights', { count: row.original.nights })}</p>
          </div>
        ),
      },
      {
        id: 'rooms',
        header: t('list.columns.rooms'),
        enableSorting: false,
        cell: ({ row }) => {
          const units = row.original.stays
            .filter((stay) => stay.status !== 'cancelled' && stay.status !== 'no_show')
            .map((stay) => unitLabel(stay.room?.number, stay.bed?.label))
          const assigned = units.filter((unit): unit is string => Boolean(unit))
          return assigned.length ? (
            <div className="flex flex-wrap gap-1">
              {assigned.map((unit) => (
                <RoomKeyTag key={unit} number={unit} status="occupied" size="sm" />
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted">{units.length ? t('list.unassigned') : '—'}</span>
          )
        },
      },
      {
        id: 'status',
        header: t('list.columns.status'),
        enableSorting: false,
        cell: ({ row }) => <StatusBadge kind="reservation" status={row.original.status} />,
      },
      {
        id: 'total_amount',
        header: t('list.columns.total'),
        meta: { align: 'right' },
        cell: ({ row }) => <MoneyText value={row.original.total_amount} currency={row.original.currency} />,
      },
      {
        id: 'balance',
        header: t('list.columns.balance'),
        meta: { align: 'right' },
        cell: ({ row }) => (
          <MoneyText
            value={row.original.balance}
            currency={row.original.currency}
            className={cn(Number(row.original.balance) > 0 ? 'font-semibold text-warning-ink' : 'text-muted')}
          />
        ),
      },
    ],
    [t, lang],
  )

  const filtered = state.view === 'all' && (state.status.length > 0 || state.from || state.to)
  const hasFilters = Boolean(filtered || state.source || state.q)

  return (
    <div ref={containerRef} className="mx-auto max-w-[1400px]">
      <PageHeader
        title={t('nav.reservations')}
        description={t('list.description')}
        actions={
          <>
            <Button onClick={() => void exportCsv()} loading={exporting}>
              <Download aria-hidden />
              {t('list.export')}
            </Button>
            {canBook && (
              <Button asChild variant="primary">
                <Link to="/app/reservations/new">
                  <Plus aria-hidden />
                  {t('actions.newReservation')}
                </Link>
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 overflow-x-auto [scrollbar-width:none]">
        <ToggleGroup
          type="single"
          value={state.view}
          onValueChange={(value) => value && update({ view: value as QuickView })}
          aria-label={t('list.views.label')}
          className="w-max"
        >
          {QUICK_VIEWS.map((view) => (
            <ToggleGroupItem key={view} value={view}>
              {t(`list.views.${view}`)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      {reservations.isError ? (
        <ErrorState error={reservations.error} onRetry={() => reservations.refetch()} className="rounded-lg border border-border bg-surface" />
      ) : (
        <DataTable
          aria-label={t('nav.reservations')}
          columns={columns}
          data={reservations.data?.results ?? []}
          getRowId={(row) => row.id}
          isLoading={reservations.isPending || reservations.isPlaceholderData}
          search={text}
          onSearchChange={setText}
          searchPlaceholder={t('list.search')}
          server={{
            rowCount: reservations.data?.count ?? 0,
            pagination,
            onPaginationChange,
            sorting,
            onSortingChange,
          }}
          onRowClick={(row) => navigate(`/app/reservations/${row.id}`)}
          empty={t(`list.empty.${state.view}`)}
          toolbar={
            <div className="flex flex-wrap items-center gap-2">
              {state.view === 'all' && (
                <Select value={state.status[0] ?? ALL} onValueChange={(value) => update({ status: value === ALL ? [] : [value] })}>
                  <SelectTrigger className="h-8 w-40" aria-label={t('list.filters.status')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>{t('list.filters.anyStatus')}</SelectItem>
                    {RESERVATION_STATUSES.map((status) => (
                      <SelectItem key={status} value={status}>
                        {t(`common:status.reservation.${status}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <Select value={state.source || ALL} onValueChange={(value) => update({ source: value === ALL ? '' : value })}>
                <SelectTrigger className="h-8 w-44" aria-label={t('list.filters.source')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('list.filters.anySource')}</SelectItem>
                  {RESERVATION_SOURCES.map((source) => (
                    <SelectItem key={source} value={source}>
                      {t(`sources.${source}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {state.view === 'all' && (
                <DateRangePicker
                  value={state.from && state.to ? { from: state.from, to: state.to } : null}
                  onChange={(range) => update({ from: range?.from ?? '', to: range?.to ?? '' })}
                  today={bd}
                  placeholder={t('list.filters.arrival')}
                  aria-label={t('list.filters.arrival')}
                  className="h-8 w-56"
                />
              )}
              {hasFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setText('')
                    setSearchParams(listStateSearch({ ...parseListState(new URLSearchParams()), view: state.view }), { replace: true })
                  }}
                >
                  <X aria-hidden />
                  {t('list.filters.clear')}
                </Button>
              )}
            </div>
          }
        />
      )}
    </div>
  )
}
