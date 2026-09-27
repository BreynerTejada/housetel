import { useMutation } from '@tanstack/react-query'
import { TriangleAlert } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api, isApiError } from '@/lib/api'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { BLOCK_KINDS, useBeds, useInvalidateInventory, type BlockKind, type Room, type RoomBlock } from '../api'
import { naturalCompare } from '../lib/text'

const WHOLE_ROOM = '__room__'

interface Range {
  from: string
  to: string
}

/** Takes a room (or one dorm bed) out of inventory for a date range (the end day is free again). */
export function BlockDialog({ room, open, onOpenChange }: { room: Room; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation('inventory')
  const { property } = useActiveProperty()
  const invalidate = useInvalidateInventory()
  const beds = useBeds(room.id, open && room.kind === 'dorm')
  const [range, setRange] = useState<Range | null>(null)
  const [kind, setKind] = useState<BlockKind>('maintenance')
  const [reason, setReason] = useState('')
  const [bed, setBed] = useState(WHOLE_ROOM)
  const [conflict, setConflict] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ids = { dates: useId(), kind: useId(), reason: useId(), bed: useId() }

  function reset(next: boolean) {
    if (!next) {
      setRange(null)
      setReason('')
      setBed(WHOLE_ROOM)
      setConflict(null)
      setError(null)
    }
    onOpenChange(next)
  }

  const create = useMutation({
    mutationFn: (force: boolean) =>
      api.post<RoomBlock>('/inventory/blocks/', {
        room: room.id,
        bed: bed === WHOLE_ROOM ? null : bed,
        start_date: range?.from,
        end_date: range?.to,
        kind,
        reason,
        force,
      }),
    onSuccess: () => {
      toast.success(t('blocks.created', { number: room.number }))
      void invalidate()
      reset(false)
    },
    onError: (err) => {
      if (isApiError(err) && err.code === 'room_has_reservations') {
        setConflict((err.data?.reservations as string[] | undefined) ?? [])
        return
      }
      setError(errorMessage(err, t))
    },
  })

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            setError(null)
            create.mutate(false)
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('blocks.newTitle', { number: room.number })}</DialogTitle>
            <DialogDescription>{t('blocks.newDescription')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-1.5">
            <span id={ids.dates} className="text-[13px] font-semibold">
              {t('blocks.dates')}
            </span>
            <DateRangePicker
              aria-label={t('blocks.dates')}
              value={range}
              onChange={(value) => {
                setRange(value)
                setConflict(null)
              }}
              today={property?.business_date}
              min={property?.business_date}
              showNights
              minNights={1}
            />
            <p className="text-xs text-muted">{t('blocks.datesHint')}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <span id={ids.kind} className="text-[13px] font-semibold">
                {t('blocks.kind')}
              </span>
              <Select name="kind" value={kind} onValueChange={(value) => setKind(value as BlockKind)}>
                <SelectTrigger aria-labelledby={ids.kind}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BLOCK_KINDS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {t(`blockKinds.${option}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {room.kind === 'dorm' && (
              <div className="grid gap-1.5">
                <span id={ids.bed} className="text-[13px] font-semibold">
                  {t('blocks.bed')}
                </span>
                <Select name="bed" value={bed} onValueChange={setBed}>
                  <SelectTrigger aria-labelledby={ids.bed}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={WHOLE_ROOM}>{t('blocks.wholeRoom')}</SelectItem>
                    {[...(beds.data ?? [])]
                      .sort((a, b) => naturalCompare(a.label, b.label))
                      .map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {t('blocks.bedLabel', { label: item.label })}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <label className="grid gap-1.5" htmlFor={ids.reason}>
            <span className="text-[13px] font-semibold">{t('blocks.reason')}</span>
            <Textarea id={ids.reason} name="reason" rows={2} maxLength={500} value={reason} placeholder={t('blocks.reasonPlaceholder')}
                      onChange={(event) => setReason(event.target.value)} />
          </label>

          {conflict && (
            <div role="alert" className="grid gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm text-warning-ink">
              <p className="flex items-start gap-2 font-semibold">
                <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                {t('blocks.conflict', { codes: conflict.join(', ') })}
              </p>
              <Button variant="secondary" size="sm" className="w-fit" loading={create.isPending} onClick={() => create.mutate(true)}>
                {t('blocks.blockAnyway')}
              </Button>
            </div>
          )}
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={() => reset(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!range || Boolean(conflict)} loading={create.isPending && !conflict}>
              {t('blocks.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
