import { BedDouble, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useRoomTypes, type RoomType } from '../api'
import { bedsSummary, sizeLabel } from '../lib/attributes'
import { naturalCompare, tr } from '../lib/text'

/** Categories at a glance: what each sells (rooms or beds), for how many people, with which beds. */
export default function RoomTypesPage() {
  const { t } = useTranslation('inventory')
  const canManage = useCan('inventory.manage')
  const roomTypes = useRoomTypes()
  const list = [...(roomTypes.data ?? [])].sort((a, b) => a.sort_order - b.sort_order || naturalCompare(a.code, b.code))
  const units = list.filter((type) => type.is_active).reduce((sum, type) => sum + type.units_count, 0)

  const newButton = canManage && (
    <Button asChild variant="primary">
      <Link to="/app/settings/room-types/new">
        <Plus aria-hidden />
        {t('roomTypes.new')}
      </Link>
    </Button>
  )

  return (
    <>
      <PageHeader
        title={t('nav.roomTypes')}
        description={roomTypes.data?.length ? t('roomTypes.description', { count: list.length, units }) : t('nav.roomTypesHint')}
        actions={newButton}
      />
      {roomTypes.isError ? (
        <ErrorState error={roomTypes.error} onRetry={() => void roomTypes.refetch()} />
      ) : !roomTypes.data ? (
        <LoadingState variant="rows" rows={4} />
      ) : list.length === 0 ? (
        <EmptyState icon={BedDouble} title={t('roomTypes.emptyTitle')} description={t('roomTypes.emptyDescription')} action={newButton} />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((type) => (
            <li key={type.id}>
              <RoomTypeCard type={type} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function RoomTypeCard({ type }: { type: RoomType }) {
  const { t, i18n } = useTranslation('inventory')
  const name = tr(type.name, i18n.language)
  const isDorm = type.kind === 'dorm'
  const capacity = isDorm
    ? t('roomTypes.perBed')
    : type.base_occupancy === type.max_occupancy
      ? t('common.people', { count: type.max_occupancy })
      : t('common.peopleRange', { min: type.base_occupancy, max: type.max_occupancy })

  return (
    <Link
      to={`/app/settings/room-types/${type.id}`}
      className={cn(
        'group flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-xs transition-[box-shadow,border-color]',
        'hover:border-border-strong hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        !type.is_active && 'opacity-75',
      )}
    >
      <div className="relative aspect-[16/9] overflow-hidden" style={{ backgroundColor: type.color }}>
        {type.cover_photo ? (
          <img src={type.cover_photo} alt="" loading="lazy" className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.02]" />
        ) : (
          <span aria-hidden className="absolute inset-0 grid place-items-center text-4xl font-bold tracking-tight text-white/85 num">
            {type.code}
          </span>
        )}
        {/* the category's tag: its color on a punched key tag */}
        <span className="absolute top-3 left-3 flex items-center gap-2 rounded-md bg-surface/95 py-1 pr-2.5 pl-2 text-[11px] font-bold shadow-xs num">
          <span aria-hidden className="size-2.5 rounded-full shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.3)]" style={{ backgroundColor: type.color }} />
          {type.code}
        </span>
        {type.photos_count > 0 && (
          <span className="absolute right-3 bottom-3 rounded-full bg-black/55 px-2 py-0.5 text-2xs font-semibold text-white">
            {t('roomTypes.photos', { count: type.photos_count })}
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-[15px] leading-6 text-fg">{name}</h2>
          <Badge tone={isDorm ? 'warning' : 'neutral'}>{t(`common.kind.${type.kind}`)}</Badge>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
          <dt className="sr-only">{t('roomTypes.units')}</dt>
          <dd className="font-semibold text-fg num">
            {isDorm ? t('common.beds', { count: type.units_count }) : t('common.rooms', { count: type.units_count })}
          </dd>
          <dt className="sr-only">{t('roomTypes.capacity')}</dt>
          <dd className="text-muted">{capacity}</dd>
          <dt className="sr-only">{t('fields.beds')}</dt>
          <dd className="col-span-2 text-muted">
            {`${bedsSummary(type.beds, t)}${type.size_m2 ? ` · ${sizeLabel(type.size_m2, i18n.language)}` : ''}`}
          </dd>
        </dl>
        <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
          {type.amenities.length > 0 && <Badge tone="outline">{t('roomTypes.amenities', { count: type.amenities.length })}</Badge>}
          {!type.is_active && <Badge tone="stone">{t('common.inactive')}</Badge>}
          {type.rooms_count > type.active_rooms_count && (
            <Badge tone="stone">{t('roomTypes.inactiveRooms', { count: type.rooms_count - type.active_rooms_count })}</Badge>
          )}
        </div>
      </div>
    </Link>
  )
}
