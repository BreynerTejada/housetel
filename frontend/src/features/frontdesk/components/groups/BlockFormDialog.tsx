import { addDays } from 'date-fns'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DatePicker, DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { parseDate, toISODate } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { createBlock, updateBlock, useRefreshFrontDesk, useRoomTypeOptions, type GroupBlock } from '../../api'
import { tr } from '../../lib/labels'
import { Counter } from '../Counter'

function minusDays(day: string, days: number): string {
  return toISODate(addDays(parseDate(day) ?? new Date(), -days))
}

/** A week before the first night, but never before today (the backend rule: today ≤ release ≤ first night). */
function defaultRelease(start: string, bd: string): string {
  const release = minusDays(start, 7)
  return release < bd ? bd : release
}

/**
 * New allotment for the group, or change one (pilot P3): the category, the nights, how many rooms (dorm: beds)
 * leave general sale for the group and the day what is not taken goes back on sale. Nights without enough rooms
 * answer 409; whoever may overbook can hold them anyway.
 */
export function BlockFormDialog({
  open,
  onOpenChange,
  groupId,
  block,
  bd,
  defaultRange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  groupId: string
  /** Editing this block (its category stays); creating one when absent. */
  block?: GroupBlock
  bd: string
  /** The group's dates, to start from (only future nights are used). */
  defaultRange?: { from: string; to: string }
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const ids = { type: useId(), dates: useId(), release: useId(), overbook: useId() }
  const refresh = useRefreshFrontDesk()
  const canOverbook = useCan('bookings.overbook')
  const roomTypes = useRoomTypeOptions(open && !block)
  const startRange =
    block
      ? { from: block.start, to: block.end }
      : defaultRange && defaultRange.from >= bd
        ? defaultRange
        : { from: toISODate(addDays(parseDate(bd) ?? new Date(), 14)), to: toISODate(addDays(parseDate(bd) ?? new Date(), 17)) }
  const [roomTypeId, setRoomTypeId] = useState<string>(block?.room_type.id ?? '')
  const [range, setRange] = useState(startRange)
  const [units, setUnits] = useState(block?.units ?? 4)
  const [release, setRelease] = useState<string | null>(block?.release_date ?? defaultRelease(startRange.from, bd))
  const [overbook, setOverbook] = useState(false)
  const [shortfall, setShortfall] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const active = (roomTypes.data ?? []).filter((item) => item.is_active).sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code))
  const type = active.find((item) => item.id === roomTypeId)
  const dorm = block ? block.room_type.kind === 'dorm' : type?.kind === 'dorm'
  const maxUnits = block ? Math.max(block.units, 500) : Math.max(1, type?.units_count ?? 1)
  const pickedMost = block ? Math.max(0, ...block.pickup.nights.map((night) => night.picked)) : 0
  const releaseMax = block ? minusDays(range.to, 1) : range.from
  const ready = Boolean((block || type) && range.to > range.from && release && release >= bd && release <= releaseMax && units >= Math.max(1, pickedMost))

  function pickType(id: string) {
    setRoomTypeId(id)
    const next = active.find((item) => item.id === id)
    if (next) setUnits((current) => Math.min(Math.max(1, current), Math.max(1, next.units_count)))
  }

  async function save() {
    if (!release) return
    setSaving(true)
    setError(null)
    try {
      if (block) {
        await updateBlock(block.id, { start: range.from, end: range.to, units, release_date: release, allow_overbooking: overbook })
        toast.success(t('groups.blocks.savedToast'))
      } else {
        await createBlock(groupId, { room_type_id: roomTypeId, start: range.from, end: range.to, units, release_date: release, allow_overbooking: overbook })
        toast.success(t('groups.blocks.createdToast', { count: units }))
      }
      await refresh()
      onOpenChange(false)
    } catch (err) {
      setShortfall(isApiError(err) && err.code === 'no_availability')
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{block ? t('groups.blocks.editTitle') : t('groups.blocks.newTitle')}</DialogTitle>
          <DialogDescription>{t('groups.blocks.formHint')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor={ids.type} className="font-semibold">
              {t('groups.blocks.roomType')}
            </Label>
            {block ? (
              <p id={ids.type} className="flex items-center gap-2 text-sm font-semibold text-fg">
                <span aria-hidden className="size-3 rounded-[4px]" style={{ backgroundColor: block.room_type.color }} />
                {tr(block.room_type.name, i18n.language)}
              </p>
            ) : (
              <Select value={roomTypeId} onValueChange={pickType}>
                <SelectTrigger id={ids.type}>
                  <SelectValue placeholder={roomTypes.isPending ? t('groups.blocks.loadingTypes') : t('groups.blocks.pickType')} />
                </SelectTrigger>
                <SelectContent>
                  {active.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {tr(item.name, i18n.language)} · {t(item.kind === 'dorm' ? 'groups.blocks.bedsCount' : 'groups.blocks.roomsCount', { count: item.units_count })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="grid gap-2">
            <Label htmlFor={ids.dates} className="font-semibold">
              {t('groups.blocks.nights')}
            </Label>
            <DateRangePicker
              id={ids.dates}
              value={range}
              onChange={(value) => {
                if (!value) return
                setRange({ from: value.from, to: value.to })
                if (!block && release && release > value.from) setRelease(defaultRelease(value.from, bd))
                setShortfall(false)
              }}
              today={bd}
              min={block ? undefined : bd}
              minNights={1}
              showNights
            />
          </div>
          <Counter
            label={dorm ? t('groups.blocks.beds') : t('groups.blocks.rooms')}
            hint={pickedMost > 0 ? t('groups.blocks.minPicked', { count: pickedMost }) : undefined}
            value={units}
            min={Math.max(1, pickedMost)}
            max={maxUnits}
            onChange={(value) => {
              setUnits(value)
              setShortfall(false)
            }}
            addLabel={t('groups.blocks.addUnit')}
            removeLabel={t('groups.blocks.removeUnit')}
          />
          <div className="grid gap-2">
            <Label htmlFor={ids.release} className="font-semibold">
              {t('groups.blocks.releaseDate')}
            </Label>
            <DatePicker id={ids.release} value={release} onChange={setRelease} min={bd} max={releaseMax} />
            <p className="text-xs text-muted">{t('groups.blocks.releaseDateHint')}</p>
          </div>
          {shortfall && canOverbook && (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-danger/25 bg-danger-soft/40 px-4 py-3">
              <Label htmlFor={ids.overbook} className="text-[13px] font-semibold">
                {t('groups.blocks.overbook')}
              </Label>
              <Switch id={ids.overbook} checked={overbook} onCheckedChange={setOverbook} />
            </div>
          )}
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={saving} disabled={!ready}>
            {block ? t('common:actions.saveChanges') : t('groups.blocks.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
