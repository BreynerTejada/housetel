import type { ColumnDef } from '@tanstack/react-table'
import { useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable, type DataTableServerOptions } from '@/components/DataTable'
import { MoneyText } from '@/components/Money'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import type { Commission } from '../api'
import { CommissionBadge } from './StatusBadges'

/** Marketplace commissions: reservation, stay, base (lodging net of taxes or the fee), rate, amount, state. */
export function CommissionsTable({
  commissions,
  isLoading,
  showOrganization = false,
  server,
  toolbar,
  search,
  onSearchChange,
  empty,
  pageSize = 10,
}: {
  commissions: Commission[]
  isLoading?: boolean
  showOrganization?: boolean
  server?: DataTableServerOptions
  toolbar?: ReactNode
  search?: string
  onSearchChange?: (value: string) => void
  empty?: ReactNode
  pageSize?: number
}) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)

  const columns = useMemo<ColumnDef<Commission>[]>(() => {
    const cols: ColumnDef<Commission>[] = [
      {
        id: 'reservation',
        accessorFn: (row) => row.reservation.code,
        header: t('commissions.reservation'),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="num font-semibold text-fg">{row.original.reservation.code}</p>
            <p className="truncate text-xs text-muted">
              {showOrganization ? `${row.original.organization.name} · ` : ''}
              {row.original.property.name}
            </p>
          </div>
        ),
      },
      {
        id: 'stay',
        accessorFn: (row) => row.reservation.checkin_date,
        header: t('commissions.stay'),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="num text-fg">
              {formatDateRange(row.original.reservation.checkin_date, row.original.reservation.checkout_date, lang)}
            </p>
            <p className="text-xs text-muted">{t(`commissions.basis.${row.original.basis}`)}</p>
          </div>
        ),
      },
      {
        id: 'base',
        accessorFn: (row) => Number(row.base_amount),
        header: t('commissions.base'),
        meta: { align: 'right' },
        cell: ({ row }) => (
          <div className="text-right">
            <MoneyText value={row.original.base_amount} className="text-fg" />
            <p className="num text-xs text-muted">× {Number(row.original.rate)} %</p>
          </div>
        ),
      },
      {
        id: 'amount',
        accessorFn: (row) => Number(row.amount),
        header: t('commissions.amount'),
        meta: { align: 'right' },
        cell: ({ row }) => (
          <MoneyText
            value={row.original.amount}
            className={row.original.status === 'reversed' ? 'text-muted line-through' : 'font-semibold text-fg'}
          />
        ),
      },
      {
        id: 'accrual',
        accessorKey: 'accrual_date',
        header: t('commissions.accrual'),
        cell: ({ row }) => <span className="num text-muted">{formatDate(row.original.accrual_date, undefined, lang)}</span>,
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: t('commissions.status'),
        cell: ({ row }) => <CommissionBadge status={row.original.status} />,
      },
    ]
    return cols
  }, [t, lang, showOrganization])

  return (
    <DataTable
      columns={columns}
      data={commissions}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      pageSize={pageSize}
      server={server}
      toolbar={toolbar}
      search={search}
      onSearchChange={onSearchChange}
      searchPlaceholder={t('commissions.searchPlaceholder')}
      empty={empty ?? t('commissions.empty')}
      aria-label={t('commissions.title')}
    />
  )
}
