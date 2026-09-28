import { useQueryClient } from '@tanstack/react-query'
import { BedDouble, Check, LoaderCircle, Pencil } from 'lucide-react'
import { useId, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { bookingKeys, setRoomingName, type GroupDetail, type RoomingRow } from '../../api'
import { splitName } from '../../lib/groups'
import { guestsLabel, tr } from '../../lib/labels'

/**
 * The rooming list (pilot P3): every room of the group's reservations with who sleeps in it — the names are
 * edited in place, the way the organizer sends them. A table on wide screens, one card per room on a phone.
 */
export function RoomingList({ group, canManage }: { group: GroupDetail; canManage: boolean }) {
  const { t } = useTranslation('frontdesk')
  const rows = group.rooming
  if (rows.length === 0) {
    return <p className="rounded-xl border border-dashed border-border-strong px-4 py-6 text-center text-[13px] text-muted">{t('groups.rooming.empty')}</p>
  }
  return (
    <>
      <div className="hidden overflow-hidden rounded-xl border border-border bg-surface shadow-xs md:block">
        <table className="w-full text-[13px]">
          <caption className="sr-only">{t('groups.rooming.caption', { name: group.name })}</caption>
          <thead className="border-b border-border bg-surface-2/60 text-left text-xs text-muted">
            <tr>
              <th scope="col" className="w-20 px-4 py-2.5 font-semibold">
                {t('groups.rooming.room')}
              </th>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                {t('groups.rooming.guest')}
              </th>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                {t('groups.rooming.roomType')}
              </th>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                {t('groups.rooming.dates')}
              </th>
              <th scope="col" className="px-4 py-2.5 font-semibold">
                {t('groups.rooming.reservation')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <RoomingTableRow key={row.stay_id} row={row} groupId={group.id} canManage={canManage} />
            ))}
          </tbody>
        </table>
      </div>
      <ul className="grid gap-2 md:hidden" aria-label={t('groups.rooming.caption', { name: group.name })}>
        {rows.map((row) => (
          <RoomingCard key={row.stay_id} row={row} groupId={group.id} canManage={canManage} />
        ))}
      </ul>
    </>
  )
}

function UnitTag({ row }: { row: RoomingRow }) {
  const { t } = useTranslation('frontdesk')
  if (!row.room) {
    return (
      <span className="inline-flex h-7 min-w-10 items-center justify-center rounded-md border border-dashed border-border-strong px-1.5 text-muted" title={t('stay.noRoom')}>
        <BedDouble aria-hidden className="size-3.5" />
        <span className="sr-only">{t('stay.noRoom')}</span>
      </span>
    )
  }
  const number = row.bed ? `${row.room.number}·${row.bed.label}` : row.room.number
  return <RoomKeyTag number={number} status={row.status === 'checked_in' ? 'occupied' : row.room.housekeeping_status} size="sm" />
}

function RoomingTableRow({ row, groupId, canManage }: { row: RoomingRow; groupId: string; canManage: boolean }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  return (
    <tr className="align-middle">
      <td className="px-4 py-2">
        <UnitTag row={row} />
      </td>
      <td className="min-w-56 px-3 py-2">
        <NameCell row={row} groupId={groupId} canManage={canManage} />
      </td>
      <td className="px-3 py-2">
        <span className="flex items-center gap-1.5 font-semibold text-fg">
          <span aria-hidden className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: row.room_type.color }} />
          {tr(row.room_type.name, i18n.language)}
          {row.group_block_id && <Badge tone="info">{t('stay.fromBlock')}</Badge>}
        </span>
        <span className="block text-xs text-muted">
          {tr(row.rate_plan.name, i18n.language)} · {guestsLabel(t, row.adults, row.children)}
        </span>
      </td>
      <td className="num px-3 py-2 text-fg">
        {formatDateRange(row.checkin, row.checkout, lang)}
        <span className="block text-xs text-muted">{t('date.nights', { count: row.nights })}</span>
      </td>
      <td className="px-4 py-2">
        <Link to={`/app/reservations/${row.reservation_id}`} className="num font-semibold text-fg underline-offset-4 hover:text-accent-ink hover:underline">
          {row.code}
        </Link>
        <span className="block max-w-48 truncate text-xs text-muted">{row.booker_name}</span>
        {row.status !== 'confirmed' && <StatusBadge kind="reservation" status={row.status} className="mt-1" />}
      </td>
    </tr>
  )
}

function RoomingCard({ row, groupId, canManage }: { row: RoomingRow; groupId: string; canManage: boolean }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  return (
    <li className="grid gap-2 rounded-xl border border-border bg-surface px-3 py-3 shadow-xs">
      <div className="flex items-start gap-3">
        <UnitTag row={row} />
        <div className="min-w-0 flex-1">
          <NameCell row={row} groupId={groupId} canManage={canManage} />
        </div>
      </div>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5 font-semibold text-fg">
          <span aria-hidden className="size-2.5 rounded-[3px]" style={{ backgroundColor: row.room_type.color }} />
          {tr(row.room_type.name, i18n.language)}
        </span>
        <span className="num">{formatDateRange(row.checkin, row.checkout, lang)}</span>
        <span>{guestsLabel(t, row.adults, row.children)}</span>
        {row.group_block_id && <Badge tone="info">{t('stay.fromBlock')}</Badge>}
      </p>
      <p className="flex items-center justify-between gap-2 text-xs">
        <Link to={`/app/reservations/${row.reservation_id}`} className="num font-semibold text-fg underline-offset-4 hover:text-accent-ink hover:underline">
          {row.code}
        </Link>
        <span className="min-w-0 truncate text-muted">{row.booker_name}</span>
      </p>
    </li>
  )
}

/**
 * The name of whoever sleeps in the room: text until it is clicked, then an input — Enter or leaving the field
 * saves, Escape gives up. Saved names replace the row in the group's cache (no refetch of the whole page).
 */
function NameCell({ row, groupId, canManage }: { row: RoomingRow; groupId: string; canManage: boolean }) {
  const { t } = useTranslation('frontdesk')
  const queryClient = useQueryClient()
  const inputId = useId()
  const current = row.guest?.full_name ?? ''
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(current)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const done = useRef(false)

  function start() {
    setValue(current)
    setError(null)
    setSaved(false)
    done.current = false
    setEditing(true)
  }

  async function commit() {
    if (done.current) return
    done.current = true
    const next = value.trim().replace(/\s+/g, ' ')
    if (next === current) {
      setEditing(false)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await setRoomingName(row.stay_id, splitName(next))
      queryClient.setQueryData<GroupDetail>(bookingKeys.group(groupId), (group) =>
        group ? { ...group, rooming: group.rooming.map((item) => (item.stay_id === row.stay_id ? { ...item, ...updated } : item)) } : group,
      )
      void queryClient.invalidateQueries({ queryKey: bookingKeys.reservation(row.reservation_id) })
      setEditing(false)
      setSaved(true)
    } catch (err) {
      done.current = false
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      void commit()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      done.current = true
      setEditing(false)
      setError(null)
    }
  }

  if (!canManage) {
    return current ? <span className="font-semibold text-fg">{current}</span> : <span className="text-muted italic">{t('groups.rooming.noName')}</span>
  }

  if (editing) {
    return (
      <div className="grid gap-1">
        <label htmlFor={inputId} className="sr-only">
          {t('groups.rooming.nameLabel', { room: row.room?.number ?? row.room_type.code })}
        </label>
        <div className="relative">
          <input
            id={inputId}
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={onKey}
            onBlur={() => void commit()}
            disabled={saving}
            placeholder={t('groups.rooming.namePlaceholder')}
            maxLength={200}
            aria-invalid={Boolean(error)}
            className="h-8 w-full rounded-md border border-accent bg-surface px-2 pr-7 text-[13px] text-fg outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          />
          {saving && <LoaderCircle aria-hidden className="absolute top-1/2 right-2 size-3.5 -translate-y-1/2 animate-spin text-muted motion-reduce:animate-none" />}
        </div>
        {error ? (
          <p role="alert" className="text-xs text-danger-ink">
            {error}
          </p>
        ) : (
          <p className="text-[11px] text-muted">{t('groups.rooming.editHint')}</p>
        )}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={start}
      aria-label={t('groups.rooming.editName', { room: row.room?.number ?? row.room_type.code, name: current || t('groups.rooming.noName') })}
      className={cn(
        'group/name -mx-1.5 flex max-w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none',
        !current && 'text-muted',
      )}
    >
      {current ? (
        <span className="truncate font-semibold text-fg">{current}</span>
      ) : (
        <span className="border-b border-dashed border-border-strong italic">{t('groups.rooming.addName')}</span>
      )}
      {saved ? (
        <Check aria-hidden className="size-3.5 shrink-0 text-success-ink" />
      ) : (
        <Pencil aria-hidden className="size-3 shrink-0 text-subtle opacity-0 transition-opacity group-hover/name:opacity-100 group-focus-visible/name:opacity-100" />
      )}
    </button>
  )
}
