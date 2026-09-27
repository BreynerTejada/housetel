import type { ColumnDef, PaginationState, SortingState } from '@tanstack/react-table'
import { Star, UserPlus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { DataTable } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Combobox } from '@/components/ui/combobox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip } from '@/components/ui/tooltip'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useGuests, useGuestTags, type GuestListParams, type GuestSummary } from '../api'
import { GuestAvatar } from '../components/GuestAvatar'
import { GuestFormDialog } from '../components/GuestFormDialog'
import { countryName, countryOptions } from '../countries'
import { formatDocument, formatPhone } from '../format'
import { useDebouncedValue } from '../hooks'

const ALL = 'all'
/** Sortable columns → API `ordering` field. */
const ORDERING: Record<string, string> = { guest: 'last_name', stays: 'stays_count', lastStay: 'last_stay_date' }

export default function GuestsPage() {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const canManage = useCan('guests.manage')
  const [params, setParams] = useSearchParams()
  // `?new=1` (⌘K "New guest") opens the form, also when the list is already on screen.
  const [creatingState, setCreatingState] = useState(false)
  const creating = creatingState || params.get('new') === '1'

  const search = params.get('q') ?? ''
  const vip = params.get('vip') === '1'
  const nationality = params.get('nationality') ?? ''
  const tag = params.get('tag') ?? ''
  const stays = params.get('stays') ?? ''
  const debouncedSearch = useDebouncedValue(search.trim(), 300)

  // Page and sorting belong to the current filters: changing a filter starts again at page 1.
  const filterKey = JSON.stringify([debouncedSearch, vip, nationality, tag, stays])
  const [pageState, setPageState] = useState({ key: filterKey, pagination: { pageIndex: 0, pageSize: 25 } })
  const pagination: PaginationState =
    pageState.key === filterKey ? pageState.pagination : { pageIndex: 0, pageSize: pageState.pagination.pageSize }
  const [sorting, setSorting] = useState<SortingState>([])

  const sort = sorting[0]
  const listParams: GuestListParams = {
    q: debouncedSearch || undefined,
    is_vip: vip || undefined,
    nationality: nationality || undefined,
    tag: tag || undefined,
    has_stays: stays === 'yes' ? true : stays === 'no' ? false : undefined,
    ordering: sort && ORDERING[sort.id] ? `${sort.desc ? '-' : ''}${ORDERING[sort.id]}` : undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  }
  const guests = useGuests(listParams)
  const tags = useGuestTags()
  const filtered = Boolean(debouncedSearch || vip || nationality || tag || stays)

  function setParam(name: string, value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(name, value)
        else next.delete(name)
        next.delete('new')
        return next
      },
      { replace: true },
    )
  }

  function setCreating(open: boolean) {
    setCreatingState(open)
    if (!open && params.get('new')) setParam('new', '')
  }

  const columns = useMemo<ColumnDef<GuestSummary>[]>(
    () => [
      {
        id: 'guest',
        header: t('list.columns.guest'),
        cell: ({ row }) => <GuestCell guest={row.original} />,
      },
      {
        id: 'contact',
        header: t('list.columns.contact'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid min-w-0 text-[13px]">
            <span className="truncate text-fg">{row.original.email || '—'}</span>
            <span className="num truncate text-muted">{formatPhone(row.original.phone)}</span>
          </div>
        ),
      },
      {
        id: 'document',
        header: t('list.columns.document'),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="num whitespace-nowrap text-[13px]">
            {formatDocument(row.original.document_type, row.original.document_number) || '—'}
          </span>
        ),
      },
      {
        id: 'country',
        header: t('list.columns.country'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px]">{countryName(row.original.nationality, lang) || '—'}</span>
            {row.original.is_foreign_non_resident && (
              <Tooltip content={t('badges.taxExemptHint')}>
                <Badge tone="info" tabIndex={0}>
                  {t('badges.taxExempt')}
                </Badge>
              </Tooltip>
            )}
          </div>
        ),
      },
      {
        id: 'stays',
        header: t('list.columns.stays'),
        meta: { align: 'right' },
        cell: ({ row }) => row.original.stays_count ?? 0,
      },
      {
        id: 'lastStay',
        header: t('list.columns.lastStay'),
        meta: { align: 'right' },
        cell: ({ row }) => (row.original.last_stay_date ? formatDate(row.original.last_stay_date, undefined, lang) : '—'),
      },
    ],
    [t, lang],
  )

  const nationalities = useMemo(() => countryOptions(lang), [lang])

  return (
    <div className="mx-auto w-full max-w-7xl">
      <PageHeader
        title={t('list.title')}
        description={t('list.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <UserPlus aria-hidden />
              {t('list.newGuest')}
            </Button>
          )
        }
      />

      <DataTable
        aria-label={t('list.tableLabel')}
        columns={columns}
        data={guests.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={guests.isPending || guests.isPlaceholderData || (guests.isError && guests.isFetching)}
        search={search}
        onSearchChange={(value) => setParam('q', value)}
        searchPlaceholder={t('list.search')}
        server={{
          rowCount: guests.data?.count ?? 0,
          pagination,
          onPaginationChange: (updater) =>
            setPageState(() => ({
              key: filterKey,
              pagination: typeof updater === 'function' ? updater(pagination) : updater,
            })),
          sorting,
          onSortingChange: setSorting,
        }}
        onRowClick={(row) => navigate(`/app/guests/${row.id}`)}
        toolbar={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={vip}
              onClick={() => setParam('vip', vip ? '' : '1')}
              className={cn(vip && 'border-accent/40 bg-accent-soft text-accent-ink hover:bg-accent-soft')}
            >
              <Star aria-hidden className={cn(vip && 'fill-accent text-accent')} />
              {t('list.filters.vipOnly')}
            </Button>
            <div className="w-56">
              <label htmlFor="guests-nationality" className="sr-only">
                {t('list.filters.nationality')}
              </label>
              <Combobox
                id="guests-nationality"
                options={nationalities}
                value={nationality || null}
                onChange={(value) => setParam('nationality', value ?? '')}
                placeholder={t('list.filters.anyNationality')}
                searchPlaceholder={t('fields.searchCountry')}
                emptyText={t('fields.noCountry')}
                className="h-8"
              />
            </div>
            <Select name="tag" value={tag || ALL} onValueChange={(value) => setParam('tag', value === ALL ? '' : value)}>
              <SelectTrigger className="h-8 w-48" aria-label={t('list.filters.tag')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('list.filters.anyTag')}</SelectItem>
                {(tags.data ?? []).map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select name="stays" value={stays || ALL} onValueChange={(value) => setParam('stays', value === ALL ? '' : value)}>
              <SelectTrigger className="h-8 w-48" aria-label={t('list.filters.stays')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('list.filters.staysAny')}</SelectItem>
                <SelectItem value="yes">{t('list.filters.staysYes')}</SelectItem>
                <SelectItem value="no">{t('list.filters.staysNo')}</SelectItem>
              </SelectContent>
            </Select>
            {filtered && (
              <Button variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                <X aria-hidden />
                {t('list.clearFilters')}
              </Button>
            )}
          </div>
        }
        empty={
          guests.isError ? (
            <ErrorState error={guests.error} onRetry={() => void guests.refetch()} className="py-0" />
          ) : filtered ? (
            t('list.emptyFiltered')
          ) : (
            t('list.empty')
          )
        }
      />

      <GuestFormDialog open={creating} onOpenChange={setCreating} onSaved={(guest) => navigate(`/app/guests/${guest.id}`)} />
    </div>
  )
}

function GuestCell({ guest }: { guest: GuestSummary }) {
  const { t } = useTranslation('guests')
  return (
    <div className="flex min-w-0 items-center gap-3">
      <GuestAvatar name={guest.full_name} vip={guest.is_vip} muted={Boolean(guest.anonymized_at)} />
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-semibold text-fg">{guest.full_name}</span>
          {guest.is_vip && <Badge tone="accent">{t('badges.vip')}</Badge>}
          {guest.blacklisted && <Badge tone="danger">{t('badges.blacklisted')}</Badge>}
          {guest.anonymized_at && <Badge tone="stone">{t('badges.anonymized')}</Badge>}
        </p>
        {(guest.city_of_residence || guest.tags.length > 0) && (
          <p className="truncate text-xs text-muted">{[guest.city_of_residence, ...guest.tags].filter(Boolean).join(' · ')}</p>
        )}
      </div>
    </div>
  )
}
