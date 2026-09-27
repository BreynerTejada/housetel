import { useMutation } from '@tanstack/react-query'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api, isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { useInvalidateInventory, type Room, type RoomType } from '../api'
import { duplicatesIn, inferFloor, parseRoomNumbers } from '../lib/roomNumbers'
import { tr } from '../lib/text'
import { RoomKeyTag } from './RoomKeyTag'

const PREVIEW_LIMIT = 60

/** Sellable beds a dorm room gets by default: its bed configuration (a bunk counts twice). */
function defaultBeds(roomType: RoomType | undefined): number {
  if (!roomType || roomType.kind !== 'dorm') return 0
  return roomType.beds.reduce((sum, bed) => sum + bed.count * (bed.type === 'bunk' ? 2 : 1), 0)
}

/**
 * Creates many rooms of one category from ranges ("101-110, 201"). The preview uses the same rules as the
 * backend, so what you see is what gets created; numbers that already exist come back marked.
 */
export function BulkCreateDialog({
  open,
  onOpenChange,
  roomTypes,
  defaultRoomTypeId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  roomTypes: RoomType[]
  defaultRoomTypeId?: string
}) {
  const { t, i18n } = useTranslation('inventory')
  const invalidate = useInvalidateInventory()
  const [roomTypeId, setRoomTypeId] = useState(defaultRoomTypeId ?? roomTypes[0]?.id ?? '')
  const [wasOpen, setWasOpen] = useState(open)
  if (open !== wasOpen) {
    // each opening starts in the category the page is filtered by (the dialog stays mounted)
    setWasOpen(open)
    if (open) setRoomTypeId(defaultRoomTypeId ?? roomTypes[0]?.id ?? '')
  }
  const [numbers, setNumbers] = useState('')
  const [floor, setFloor] = useState('')
  const [building, setBuilding] = useState('')
  const roomType = roomTypes.find((type) => type.id === roomTypeId)
  const [beds, setBeds] = useState<number | null>(null)
  const bedsPerRoom = beds ?? defaultBeds(roomType)
  const [existing, setExisting] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const ids = { type: useId(), numbers: useId(), floor: useId(), building: useId(), beds: useId(), hint: useId() }

  const parsed = useMemo(() => parseRoomNumbers(numbers), [numbers])
  const repeated = useMemo(() => duplicatesIn(parsed.numbers), [parsed.numbers])
  const floors = useMemo(() => {
    if (floor.trim()) return [floor.trim()]
    return [...new Set(parsed.numbers.map(inferFloor).filter(Boolean))].sort((a, b) => Number(a) - Number(b))
  }, [floor, parsed.numbers])
  const floorList = new Intl.ListFormat(i18n.language.startsWith('en') ? 'en' : 'es', { type: 'conjunction' }).format(floors)

  function close(next: boolean) {
    if (!next) {
      setNumbers('')
      setFloor('')
      setBuilding('')
      setBeds(null)
      setExisting([])
      setError(null)
    }
    onOpenChange(next)
  }

  const create = useMutation({
    mutationFn: () =>
      api.post<{ count: number; rooms: Room[] }>('/inventory/rooms/bulk-create/', {
        room_type: roomTypeId,
        numbers,
        floor: floor.trim() || null,
        building: building.trim(),
        beds_per_room: roomType?.kind === 'dorm' ? bedsPerRoom : null,
      }),
    onSuccess: (result) => {
      toast.success(t('bulkCreate.created', { count: result.count }))
      void invalidate()
      close(false)
    },
    onError: (err) => {
      if (isApiError(err) && err.code === 'duplicate_room_numbers') {
        setExisting((err.data?.duplicates as string[] | undefined) ?? [])
        setError(null)
        return
      }
      setError(errorMessage(err, t))
    },
  })

  const parseMessage = numbers.trim() && parsed.error ? t(`bulkCreate.errors.${parsed.error.code}`, { part: parsed.error.part ?? '' }) : null
  const blocked = !roomTypeId || !parsed.numbers.length || Boolean(parsed.error) || repeated.length > 0
  const conflict = existing.filter((number) => parsed.numbers.includes(number))

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-2xl">
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (!blocked) create.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('bulkCreate.title')}</DialogTitle>
            <DialogDescription>{t('bulkCreate.description')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem_10rem]">
            <div className="grid gap-1.5 sm:col-span-3">
              <span id={ids.type} className="text-[13px] font-semibold">
                {t('fields.room_type')}
              </span>
              <Select name="room_type" value={roomTypeId} onValueChange={(value) => { setRoomTypeId(value); setBeds(null) }}>
                <SelectTrigger aria-labelledby={ids.type}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {roomTypes.map((type) => (
                    <SelectItem key={type.id} value={type.id}>
                      {type.code} · {tr(type.name, i18n.language)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="grid gap-1.5" htmlFor={ids.numbers}>
              <span className="text-[13px] font-semibold">{t('bulkCreate.numbers')}</span>
              <Input
                id={ids.numbers}
                name="numbers"
                autoComplete="off"
                placeholder="101-110, 201-208"
                aria-invalid={Boolean(parseMessage) || repeated.length > 0 || conflict.length > 0}
                aria-describedby={ids.hint}
                value={numbers}
                onChange={(event) => {
                  setNumbers(event.target.value)
                  setExisting([])
                }}
              />
            </label>
            <label className="grid gap-1.5" htmlFor={ids.floor}>
              <span className="text-[13px] font-semibold">{t('fields.floor')}</span>
              <Input id={ids.floor} name="floor" maxLength={20} placeholder={t('bulkCreate.floorAuto')} value={floor}
                     onChange={(event) => setFloor(event.target.value)} />
            </label>
            <label className="grid gap-1.5" htmlFor={ids.building}>
              <span className="text-[13px] font-semibold">{t('fields.building')}</span>
              <Input id={ids.building} name="building" maxLength={50} placeholder={t('bulkCreate.optional')} value={building}
                     onChange={(event) => setBuilding(event.target.value)} />
            </label>
            <p id={ids.hint} className="text-xs text-muted sm:col-span-3">
              {t('bulkCreate.hint')}
            </p>
            {roomType?.kind === 'dorm' && (
              <label className="grid gap-1.5 sm:col-span-3 sm:max-w-56" htmlFor={ids.beds}>
                <span className="text-[13px] font-semibold">{t('bulkCreate.bedsPerRoom')}</span>
                <Input id={ids.beds} name="beds_per_room" type="number" min={0} max={50} value={bedsPerRoom}
                       onChange={(event) => setBeds(Number.isFinite(event.target.valueAsNumber) ? event.target.valueAsNumber : 0)} />
              </label>
            )}
          </div>

          <section aria-live="polite" className="grid gap-2 rounded-lg border border-border bg-surface-2/60 p-3">
            {parseMessage ? (
              <p className="text-sm font-medium text-danger-ink">{parseMessage}</p>
            ) : parsed.numbers.length > 0 ? (
              <>
                <p className="text-[13px] font-semibold text-fg">
                  {t('common.rooms', { count: parsed.numbers.length })} ·{' '}
                  {floors.length ? t('bulkCreate.floors', { count: floors.length, floors: floorList }) : t('bulkCreate.noFloor')}
                </p>
                <ul aria-label={t('bulkCreate.preview')} className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
                  {parsed.numbers.slice(0, PREVIEW_LIMIT).map((number, index) => {
                    const duplicate = repeated.includes(number) || conflict.includes(number)
                    return (
                      <li key={`${number}-${index}`} data-duplicate={duplicate || undefined}>
                        <RoomKeyTag number={number} size="sm" className={cn(duplicate && 'bg-danger-soft text-danger-ink ring-1 ring-danger/40')} />
                      </li>
                    )
                  })}
                </ul>
                {parsed.numbers.length > PREVIEW_LIMIT && (
                  <p className="text-xs text-muted">{t('bulkCreate.more', { count: parsed.numbers.length - PREVIEW_LIMIT })}</p>
                )}
                {repeated.length > 0 && (
                  <p className="text-sm font-medium text-danger-ink">{t('bulkCreate.repeated', { count: repeated.length, numbers: repeated.join(', ') })}</p>
                )}
                {conflict.length > 0 && (
                  <p className="text-sm font-medium text-danger-ink">{t('bulkCreate.existing', { numbers: conflict.join(', ') })}</p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">{t('bulkCreate.empty')}</p>
            )}
          </section>

          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={() => close(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={blocked || conflict.length > 0} loading={create.isPending}>
              {t('bulkCreate.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
