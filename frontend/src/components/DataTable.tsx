import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type PaginationState,
  type RowData,
  type RowSelectionState,
  type SortingState,
} from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { LoadingState } from './LoadingState'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'
import { ToggleGroup, ToggleGroupItem } from './ui/toggle-group'

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Numbers and money read better right-aligned. */
    align?: 'left' | 'right' | 'center'
    className?: string
  }
}

export interface DataTableServerOptions {
  /** Total rows on the server (`count` of the paginated API response). */
  rowCount: number
  pagination: PaginationState
  onPaginationChange: OnChangeFn<PaginationState>
  sorting?: SortingState
  onSortingChange?: OnChangeFn<SortingState>
}

export interface DataTableProps<T> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<T, any>[]
  data: T[]
  getRowId?: (row: T, index: number) => string
  isLoading?: boolean
  /** Client-side search over every column. */
  enableSearch?: boolean
  searchPlaceholder?: string
  /** Controlled search (server-side filtering); shows the search box too. */
  search?: string
  onSearchChange?: (value: string) => void
  /** Client-side page size (default 25). */
  pageSize?: number
  /** Server-side pagination/sorting (DRF `?page=&page_size=`); page index is 0-based here. */
  server?: DataTableServerOptions
  enableSelection?: boolean
  onSelectionChange?: (rows: T[]) => void
  onRowClick?: (row: T) => void
  enableDensityToggle?: boolean
  initialDensity?: 'comfortable' | 'compact'
  /** Filters and actions shown next to the search box. */
  toolbar?: ReactNode
  empty?: ReactNode
  className?: string
  'aria-label'?: string
}

const PAGE_SIZES = [10, 25, 50, 100]

export function DataTable<T>({
  columns,
  data,
  getRowId,
  isLoading = false,
  enableSearch = false,
  searchPlaceholder,
  search,
  onSearchChange,
  pageSize = 25,
  server,
  enableSelection = false,
  onSelectionChange,
  onRowClick,
  enableDensityToggle = false,
  initialDensity = 'comfortable',
  toolbar,
  empty,
  className,
  'aria-label': ariaLabel,
}: DataTableProps<T>) {
  const { t } = useTranslation()
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize })
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [density, setDensity] = useState(initialDensity)

  const allColumns = useMemo<ColumnDef<T, unknown>[]>(() => {
    if (!enableSelection) return columns
    const select: ColumnDef<T, unknown> = {
      id: '__select',
      enableSorting: false,
      header: ({ table }) => (
        <Checkbox
          aria-label={t('table.selectAll')}
          checked={table.getIsAllRowsSelected() ? true : table.getIsSomeRowsSelected() ? 'indeterminate' : false}
          onCheckedChange={(value) => table.toggleAllRowsSelected(value === true)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          aria-label={t('table.selectRow')}
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(value === true)}
          onClick={(event) => event.stopPropagation()}
        />
      ),
    }
    return [select, ...columns]
  }, [columns, enableSelection, t])

  const table = useReactTable({
    data,
    columns: allColumns,
    getRowId,
    state: {
      sorting: server?.sorting ?? sorting,
      globalFilter,
      pagination: server?.pagination ?? pagination,
      rowSelection,
    },
    sortDescFirst: false,
    enableRowSelection: enableSelection,
    onSortingChange: server?.onSortingChange ?? setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: server?.onPaginationChange ?? setPagination,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: server?.onSortingChange ? undefined : getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: server ? undefined : getPaginationRowModel(),
    manualPagination: Boolean(server),
    manualSorting: Boolean(server?.onSortingChange),
    rowCount: server?.rowCount,
    autoResetPageIndex: !server,
  })

  // Report selection changes (not the initial empty selection).
  const reportedSelection = useRef(rowSelection)
  useEffect(() => {
    if (reportedSelection.current === rowSelection) return
    reportedSelection.current = rowSelection
    onSelectionChange?.(table.getSelectedRowModel().flatRows.map((row) => row.original))
  }, [rowSelection, onSelectionChange, table])

  const rows = table.getRowModel().rows
  const state = table.getState().pagination
  const pageCount = Math.max(1, table.getPageCount())
  const total = server ? server.rowCount : table.getFilteredRowModel().rows.length
  const selectedCount = Object.keys(rowSelection).length
  const showSearch = enableSearch || Boolean(onSearchChange)
  const searchValue = onSearchChange ? (search ?? '') : globalFilter
  const filtering = searchValue.trim().length > 0
  const cellPadding = density === 'compact' ? 'py-1.5' : 'py-2.5'

  return (
    <div className={cn('overflow-hidden rounded-lg border border-border bg-surface shadow-xs', className)}>
      {(showSearch || toolbar || enableDensityToggle) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          {showSearch && (
            <Input
              type="search"
              name="search"
              value={searchValue}
              onChange={(event) => (onSearchChange ? onSearchChange(event.target.value) : setGlobalFilter(event.target.value))}
              placeholder={searchPlaceholder ?? t('table.search')}
              aria-label={searchPlaceholder ?? t('table.search')}
              className="h-8 w-full sm:w-64"
            />
          )}
          {toolbar}
          {enableDensityToggle && (
            <ToggleGroup
              type="single"
              value={density}
              onValueChange={(value) => value && setDensity(value as typeof density)}
              aria-label={t('table.density')}
              className="ml-auto"
            >
              <ToggleGroupItem value="comfortable">{t('table.comfortable')}</ToggleGroupItem>
              <ToggleGroupItem value="compact">{t('table.compact')}</ToggleGroupItem>
            </ToggleGroup>
          )}
        </div>
      )}

      <Table aria-label={ariaLabel} aria-busy={isLoading || undefined} className={cn(isLoading && rows.length > 0 && 'opacity-60')}>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id} className="hover:bg-transparent">
              {group.headers.map((header) => {
                const meta = header.column.columnDef.meta
                const sorted = header.column.getIsSorted()
                const label = header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())
                return (
                  <TableHead
                    key={header.id}
                    aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    className={cn(meta?.align === 'right' && 'text-right', meta?.align === 'center' && 'text-center', meta?.className)}
                  >
                    {header.column.getCanSort() ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={cn(
                          '-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                          sorted && 'text-fg',
                        )}
                      >
                        {label}
                        {sorted === 'asc' ? (
                          <ArrowUp aria-hidden className="size-3.5" />
                        ) : sorted === 'desc' ? (
                          <ArrowDown aria-hidden className="size-3.5" />
                        ) : (
                          <ArrowUpDown aria-hidden className="size-3.5 opacity-40" />
                        )}
                      </button>
                    ) : (
                      label
                    )}
                  </TableHead>
                )
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={allColumns.length} className="p-0">
                {isLoading ? (
                  <LoadingState variant="rows" rows={4} />
                ) : (
                  <div className="px-6 py-12 text-center text-sm text-muted">
                    {filtering && data.length > 0 ? t('table.emptyFiltered') : (empty ?? t('table.empty'))}
                  </div>
                )}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow
                key={row.id}
                data-state={row.getIsSelected() ? 'selected' : undefined}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === 'Enter') onRowClick(row.original)
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                className={cn(onRowClick && 'cursor-pointer focus-visible:bg-surface-2 focus-visible:outline-none')}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta
                  return (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        cellPadding,
                        meta?.align === 'right' && 'num text-right',
                        meta?.align === 'center' && 'text-center',
                        meta?.className,
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-3 py-2 text-[13px] text-muted">
        <p className="num">
          {t('table.total', { count: total })}
          {selectedCount > 0 && (
            <>
              <span aria-hidden className="mx-2 text-subtle">
                ·
              </span>
              <span className="font-semibold text-accent-ink">{t('table.selected', { count: selectedCount })}</span>
            </>
          )}
        </p>
        <div className="flex items-center gap-3">
          <label className="hidden items-center gap-2 sm:flex">
            <span>{t('table.rowsPerPage')}</span>
            <Select value={String(state.pageSize)} onValueChange={(value) => table.setPageSize(Number(value))}>
              <SelectTrigger className="h-8 w-[4.5rem]" aria-label={t('table.rowsPerPage')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <span className="num">{t('table.pageOf', { page: state.pageIndex + 1, pages: pageCount })}</span>
          <div className="flex items-center gap-1">
            <Button
              variant="secondary"
              size="icon-sm"
              aria-label={t('table.previous')}
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ChevronLeft aria-hidden />
            </Button>
            <Button
              variant="secondary"
              size="icon-sm"
              aria-label={t('table.next')}
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ChevronRight aria-hidden />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
