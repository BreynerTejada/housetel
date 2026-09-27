import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { DataTable } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { useActiveProperty } from '@/lib/auth'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useGuestStays, type GuestStay } from '../api'

/** Reservations of the guest (as booker or companion) in every hotel of the chain, newest first. */
export function StaysPanel({ guestId }: { guestId: string }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const stays = useGuestStays(guestId, pagination.pageIndex + 1)

  const columns = useMemo<ColumnDef<GuestStay>[]>(
    () => [
      {
        id: 'code',
        header: t('stays.code'),
        enableSorting: false,
        cell: ({ row }) =>
          // Reservations of another hotel of the chain open from that hotel (the staff API is per property).
          row.original.property.id === property?.id ? (
            <Link to={`/app/reservations/${row.original.id}`} className="num font-semibold text-accent-ink underline-offset-4 hover:underline">
              {row.original.code}
            </Link>
          ) : (
            <span className="num font-semibold text-fg">{row.original.code}</span>
          ),
      },
      {
        id: 'property',
        header: t('stays.property'),
        enableSorting: false,
        cell: ({ row }) => <span className="text-[13px]">{row.original.property.name}</span>,
      },
      {
        id: 'dates',
        header: t('stays.dates'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid">
            <span className="num text-[13px] text-fg">{formatDateRange(row.original.checkin, row.original.checkout, lang)}</span>
            <span className="text-xs text-muted">{t('stays.nights', { count: row.original.nights })}</span>
          </div>
        ),
      },
      {
        id: 'status',
        header: t('stays.status'),
        enableSorting: false,
        cell: ({ row }) => <StatusBadge kind="reservation" status={row.original.status} />,
      },
      {
        id: 'role',
        header: t('stays.role'),
        enableSorting: false,
        cell: ({ row }) => (
          <Badge tone={row.original.role === 'booker' ? 'outline' : 'neutral'}>
            {row.original.role === 'booker' ? t('stays.booker') : t('stays.occupant')}
          </Badge>
        ),
      },
      {
        id: 'rooms',
        header: t('stays.rooms'),
        enableSorting: false,
        cell: ({ row }) => <span className="num text-[13px]">{row.original.rooms.join(', ') || '—'}</span>,
      },
      {
        id: 'total',
        header: t('stays.total'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => <MoneyText value={row.original.total_amount} currency={row.original.currency} />,
      },
    ],
    [t, lang, property?.id],
  )

  return (
    <DataTable
      aria-label={t('stays.tableLabel')}
      columns={columns}
      data={stays.data?.results ?? []}
      getRowId={(row) => row.id}
      isLoading={stays.isPending || (stays.isError && stays.isFetching)}
      server={{ rowCount: stays.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
      empty={
        stays.isError ? <ErrorState error={stays.error} onRetry={() => void stays.refetch()} className="py-0" /> : t('stays.empty')
      }
    />
  )
}
