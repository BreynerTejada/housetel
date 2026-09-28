import { ChevronRight, Plus, Search, UsersRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useDebouncedValue } from '@/features/guests/hooks'
import { useActiveProperty } from '@/lib/auth'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useGroups, type GroupListItem, type GroupWhen } from '../api'
import { GroupFormDialog } from '../components/groups/GroupFormDialog'
import { PickupMeter } from '../components/groups/PickupMeter'
import { GROUP_STATE_TONE, groupNights } from '../lib/groups'

const WHEN: GroupWhen[] = ['upcoming', 'past', 'all']
const PAGE_SIZE = 50

/**
 * `/app/groups` (pilot P3): weddings, congresses and delegations — dates, rooms, allotment pickup and what they
 * owe, upcoming ones first. A group opens its rooming list, reservations and allotments.
 */
export default function GroupsPage() {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const when = (WHEN as string[]).includes(searchParams.get('when') ?? '') ? (searchParams.get('when') as GroupWhen) : 'upcoming'
  const [text, setText] = useState(searchParams.get('q') ?? '')
  const q = useDebouncedValue(text, 300).trim()
  const params = useMemo(() => ({ when, q: q || undefined, page_size: PAGE_SIZE }), [when, q])
  const groups = useGroups(params)
  const canManage = useCan('bookings.manage')
  const [creating, setCreating] = useState(false)
  const { property } = useActiveProperty()
  const currency = property?.currency || 'COP'

  return (
    <div className="mx-auto max-w-[1200px]">
      <PageHeader
        title={t('groups.title')}
        description={t('groups.description')}
        actions={
          canManage && (
            <>
              <Button onClick={() => setCreating(true)}>
                <Plus aria-hidden />
                {t('groups.new')}
              </Button>
              <Button asChild variant="primary">
                <Link to="/app/reservations/new?group_mode=1">
                  <UsersRound aria-hidden />
                  {t('groups.newReservation')}
                </Link>
              </Button>
            </>
          )
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="overflow-x-auto [scrollbar-width:none]">
          <ToggleGroup
            type="single"
            value={when}
            onValueChange={(value) => value && setSearchParams(value === 'upcoming' ? {} : { when: value }, { replace: true })}
            aria-label={t('groups.when.label')}
            className="w-max"
          >
            {WHEN.map((value) => (
              <ToggleGroupItem key={value} value={value}>
                {t(`groups.when.${value}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <label className="relative block sm:w-72">
          <span className="sr-only">{t('groups.search')}</span>
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <Input type="search" value={text} onChange={(event) => setText(event.target.value)} placeholder={t('groups.search')} className="pl-9" />
        </label>
      </div>

      {groups.isError ? (
        <ErrorState error={groups.error} onRetry={() => groups.refetch()} className="rounded-xl border border-border bg-surface" />
      ) : !groups.data ? (
        <LoadingState variant="rows" rows={4} />
      ) : groups.data.results.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface">
          <EmptyState
            icon={UsersRound}
            title={t(q ? 'groups.emptySearch' : `groups.empty.${when}`)}
            description={t('groups.emptyHint')}
            action={
              canManage && (
                <Button onClick={() => setCreating(true)}>
                  <Plus aria-hidden />
                  {t('groups.new')}
                </Button>
              )
            }
          />
        </div>
      ) : (
        <ul className={cn('grid gap-2', groups.isPlaceholderData && 'opacity-70')} aria-label={t('groups.title')}>
          {groups.data.results.map((group) => (
            <GroupRow key={group.id} group={group} lang={lang} currency={currency} onOpen={() => navigate(`/app/groups/${group.id}`)} />
          ))}
        </ul>
      )}
      {creating && (
        <GroupFormDialog
          open
          onOpenChange={(open) => !open && setCreating(false)}
          onSaved={(group) => navigate(`/app/groups/${group.id}`)}
        />
      )}
    </div>
  )
}

function GroupRow({ group, lang, currency, onOpen }: { group: GroupListItem; lang: 'es' | 'en'; currency: string; onOpen: () => void }) {
  const { t } = useTranslation('frontdesk')
  const figures = group.figures
  const nights = groupNights(figures)
  const balance = Number(figures?.balance ?? 0)
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface px-4 py-3.5 text-left shadow-xs transition-colors hover:border-border-strong focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none md:grid-cols-[minmax(0,2.2fr)_minmax(0,1.4fr)_minmax(0,0.8fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto]"
      >
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate font-semibold text-fg">{group.name}</span>
            {figures && figures.state !== 'empty' && (
              <Badge tone={GROUP_STATE_TONE[figures.state]} className="shrink-0">
                {t(`groups.state.${figures.state}`)}
              </Badge>
            )}
          </span>
          <span className="block truncate text-[13px] text-muted">
            {group.contact_guest ? t('groups.contact', { name: group.contact_guest.full_name }) : t('groups.noContact')}
          </span>
        </span>
        <ChevronRight aria-hidden className="size-4 text-subtle md:order-last" />
        <span className="num text-[13px] md:text-sm">
          {figures?.start && figures.end ? (
            <>
              <span className="block text-fg">{formatDateRange(figures.start, figures.end, lang)}</span>
              <span className="block text-xs text-muted">{t('common:date.nights', { count: nights })}</span>
            </>
          ) : (
            <span className="text-muted">{t('groups.noDates')}</span>
          )}
        </span>
        <span className="text-[13px]">
          <span className="num block font-semibold text-fg">{t('groups.rooms', { count: figures?.rooms ?? 0 })}</span>
          <span className="block text-xs text-muted">{t('groups.reservations', { count: figures?.reservations ?? 0 })}</span>
        </span>
        <span className="min-w-0">
          {figures && figures.blocks > 0 ? (
            <PickupMeter picked={figures.picked_room_nights} total={figures.room_nights} pct={figures.pickup_pct} rooms={figures.picked_rooms} units={figures.blocked_units} compact />
          ) : (
            <span className="text-xs text-muted">{t('groups.noBlocks')}</span>
          )}
        </span>
        <span className="text-right md:text-left">
          <span className="block text-xs text-muted">{t('groups.balance')}</span>
          <MoneyText value={figures?.balance ?? '0'} currency={currency} className={cn('num text-[13px] font-semibold', balance > 0 ? 'text-warning-ink' : 'text-fg')} />
        </span>
      </button>
    </li>
  )
}
