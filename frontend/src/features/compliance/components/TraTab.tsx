import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { IdCard, RotateCcw, UserPen } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { DataTable } from '@/components/DataTable'
import { DatePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useRetryTra, useTraRegistrations, type TraRegistration, type TraStatus } from '../api'
import { MissingFields, SimulatedBadge, TraStatusBadge } from './common'
import { useDebounced } from '../hooks'

const STATUSES: TraStatus[] = ['registered', 'pending', 'error']
const ALL = 'all'

export function RetryTraButton({ registration, size = 'sm' }: { registration: Pick<TraRegistration, 'id' | 'status'>; size?: 'sm' | 'icon-sm' }) {
  const { t } = useTranslation('compliance')
  const retry = useRetryTra()
  const canTra = useCan('compliance.tra')
  if (!canTra || registration.status === 'registered') return null
  return (
    <Button
      size={size}
      loading={retry.isPending}
      aria-label={size === 'icon-sm' ? t('tra.retry') : undefined}
      onClick={async (event) => {
        event.stopPropagation()
        try {
          const result = await retry.mutateAsync(registration.id)
          if (result.status === 'registered') toast.success(t('tra.registeredToast', { number: result.tra_number }))
          else toast.warning(result.error || t(`traStatus.${result.status}`))
        } catch (error) {
          toast.error(errorMessage(error, t))
        }
      }}
    >
      {!retry.isPending && <RotateCcw aria-hidden />}
      {size === 'sm' && t('tra.retry')}
    </Button>
  )
}

/** Tab "TRA": one registration per guest at check-in (main guest and companions), with what is missing. */
export function TraTab({ initialStatus }: { initialStatus?: TraStatus }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<TraStatus | typeof ALL>(initialStatus ?? ALL)
  const [date, setDate] = useState<string | null>(null)
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const q = useDebounced(search.trim())
  const firstPage = () => setPagination((current) => ({ ...current, pageIndex: 0 }))
  const query = useTraRegistrations({
    q: q || undefined,
    status: status === ALL ? undefined : status,
    date: date ?? undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  })

  const columns = useMemo<ColumnDef<TraRegistration>[]>(
    () => [
      {
        id: 'guest',
        header: t('tra.guest'),
        cell: ({ row }) => (
          <div className="min-w-44">
            <p className="flex flex-wrap items-center gap-1.5 text-fg">
              <span className="font-semibold">{row.original.guest.full_name}</span>
              <Badge tone={row.original.is_main ? 'info' : 'neutral'}>{t(row.original.is_main ? 'tra.main' : 'tra.companion')}</Badge>
            </p>
            <p className="num text-xs text-muted">
              {[row.original.guest.document_type, row.original.guest.document_number].filter(Boolean).join(' ') || t('tra.noDocument')}
            </p>
            <TraStatusBadge status={row.original.status} className="mt-1 sm:hidden" />
          </div>
        ),
      },
      {
        accessorKey: 'reservation_code',
        header: t('tra.reservation'),
        cell: ({ row }) => (
          <Link to={`/app/reservations/${row.original.reservation_id}`} className="num font-semibold text-accent-ink hover:underline">
            {row.original.reservation_code}
          </Link>
        ),
      },
      { accessorKey: 'room', header: t('tra.room'), cell: ({ row }) => <span className="num">{row.original.room || '—'}</span> },
      {
        accessorKey: 'checkin_date',
        header: t('tra.checkin'),
        cell: ({ row }) => <span className="num whitespace-nowrap">{formatDate(row.original.checkin_date, undefined, lang)}</span>,
      },
      {
        accessorKey: 'status',
        header: t('tra.status'),
        meta: { className: 'hidden sm:table-cell' },
        cell: ({ row }) => (
          <div className="grid gap-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <TraStatusBadge status={row.original.status} />
              <SimulatedBadge mode={row.original.mode} className="hidden xl:inline-flex" />
            </div>
            {row.original.status !== 'registered' && row.original.missing_fields.length === 0 && row.original.error && (
              <p className="max-w-64 text-xs text-muted">{row.original.error}</p>
            )}
            <MissingFields fields={row.original.missing_fields} scope="tra" />
          </div>
        ),
      },
      {
        accessorKey: 'tra_number',
        header: t('tra.number'),
        cell: ({ row }) => <span className="num text-[13px] font-semibold">{row.original.tra_number || '—'}</span>,
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">{t('actionsLabel')}</span>,
        meta: { align: 'right' },
        cell: ({ row }) =>
          row.original.status === 'registered' ? null : (
            <div className="flex justify-end gap-1">
              {row.original.missing_fields.length > 0 && (
                <Button asChild size="icon-sm" variant="ghost" aria-label={t('missing.fixFor', { name: row.original.guest.full_name })}>
                  <Link to={`/app/guests/${row.original.guest.id}`}>
                    <UserPen aria-hidden />
                  </Link>
                </Button>
              )}
              <RetryTraButton registration={row.original} size="icon-sm" />
            </div>
          ),
      },
    ],
    [t, lang],
  )

  const toolbar = (
    <>
      <Select
        value={status}
        onValueChange={(value) => {
          setStatus(value as TraStatus | typeof ALL)
          firstPage()
        }}
        name="tra-status"
      >
        <SelectTrigger className="h-8 w-full sm:w-44" aria-label={t('tra.status')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{t('tra.allStatuses')}</SelectItem>
          {STATUSES.map((value) => (
            <SelectItem key={value} value={value}>
              {t(`traStatus.${value}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <DatePicker
        value={date}
        onChange={(value) => {
          setDate(value)
          firstPage()
        }}
        placeholder={t('tra.anyArrival')}
        aria-label={t('tra.checkin')}
        className="h-8 w-full sm:w-52"
      />
      {date && (
        <Button size="sm" variant="ghost" onClick={() => setDate(null)}>
          {t('common:actions.clear')}
        </Button>
      )}
    </>
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      <p className="text-[13px] text-muted">{t('tra.hint')}</p>
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('tra.title')}
          columns={columns}
          data={query.data?.results ?? []}
          isLoading={query.isPending || query.isFetching}
          getRowId={(row) => row.id}
          search={search}
          onSearchChange={(value) => {
            setSearch(value)
            firstPage()
          }}
          searchPlaceholder={t('tra.search')}
          toolbar={toolbar}
          server={{ rowCount: query.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
          empty={<EmptyState icon={IdCard} title={t('tra.empty')} description={t('tra.emptyHint')} />}
        />
      )}
    </div>
  )
}
