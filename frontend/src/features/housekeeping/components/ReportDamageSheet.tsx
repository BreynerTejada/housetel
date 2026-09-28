import { addDays, format, isValid, parseISO } from 'date-fns'
import { ImagePlus, TriangleAlert, X } from 'lucide-react'
import { useEffect, useId, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DatePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useMediaQuery } from '@/lib/hooks'
import { PRIORITIES, createTicket, useHkMutation, type Priority, type RoomRef, type TicketInput, type Technician } from '../api'

const NONE = 'none'
const MAX_PHOTOS = 6

function nextDay(date: string): string | null {
  const day = parseISO(date)
  return isValid(day) ? format(addDays(day, 1), 'yyyy-MM-dd') : null
}

function objectUrl(file: File): string | null {
  try {
    return URL.createObjectURL(file)
  } catch {
    return null // environments without Blob URLs: the chip shows the file name instead
  }
}

/** Object URLs for the chosen photos (thumbnails), revoked when they change. */
function usePreviews(files: File[]) {
  const urls = useMemo(() => files.map(objectUrl), [files])
  useEffect(() => () => urls.forEach((url) => url && URL.revokeObjectURL(url)), [urls])
  return urls
}

/**
 * "Report damage": what happened, photos straight from the phone camera and, when the room cannot be sold,
 * a block until it is fixed. `room` fixes the room (from a task or the board); `rooms` lets the reporter pick
 * one (or a common area). Maintenance and supervisors (`canForce`) may block over bookings after a warning.
 */
export function ReportDamageSheet({
  open,
  onOpenChange,
  ...form
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  businessDate: string
  room?: RoomRef | null
  rooms?: RoomRef[]
  technicians?: Technician[]
  canForce?: boolean
}) {
  const isPhone = useMediaQuery('(max-width: 639px)')
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={isPhone ? 'bottom' : 'right'} className={isPhone ? 'h-[92dvh]' : undefined}>
        {/* Mounted with the sheet: every report starts from an empty form. */}
        <ReportForm {...form} onDone={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}

function ReportForm({
  businessDate,
  room = null,
  rooms,
  technicians,
  canForce = false,
  onDone,
}: {
  businessDate: string
  room?: RoomRef | null
  rooms?: RoomRef[]
  technicians?: Technician[]
  canForce?: boolean
  onDone: () => void
}) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('normal')
  const [roomId, setRoomId] = useState<string>(NONE)
  const [location, setLocation] = useState('')
  const [assigneeId, setAssigneeId] = useState<string>(NONE)
  const [blocksRoom, setBlocksRoom] = useState(false)
  const [until, setUntil] = useState<string | null>(nextDay(businessDate))
  const [photos, setPhotos] = useState<File[]>([])
  const [titleError, setTitleError] = useState(false)
  const previews = usePreviews(photos)

  const chosenRoom = room ?? rooms?.find((candidate) => candidate.id === roomId) ?? null
  const report = useHkMutation((input: TicketInput) => createTicket(input), {
    onSuccess: () => {
      toast.success(t('report.sent'))
      onDone()
    },
  })
  const needsForce = isApiError(report.error) && report.error.code === 'room_has_reservations'

  function send(force: boolean) {
    if (!title.trim()) {
      setTitleError(true)
      return
    }
    report.mutate({
      title: title.trim(),
      description: description.trim(),
      priority,
      room_id: chosenRoom?.id ?? null,
      location: chosenRoom ? '' : location.trim(),
      blocks_room: Boolean(chosenRoom) && blocksRoom,
      blocked_until: chosenRoom && blocksRoom ? until : null,
      assigned_to_id: assigneeId === NONE ? null : assigneeId,
      force: force || undefined,
      photos,
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    send(false)
  }

  function addPhotos(list: FileList | null) {
    if (!list) return
    setPhotos((current) => [...current, ...Array.from(list)].slice(0, MAX_PHOTOS))
  }

  return (
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col" noValidate>
          <SheetHeader>
            <SheetTitle>{t('report.title')}</SheetTitle>
            <SheetDescription>
              {room ? t('card.room', { number: room.number }) : t('report.description')}
            </SheetDescription>
          </SheetHeader>
          <SheetBody className="grid content-start gap-5">
            {!room && rooms && (
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-room`}>{t('report.room')}</Label>
                <Select name="room_id" value={roomId} onValueChange={setRoomId}>
                  <SelectTrigger id={`${ids}-room`} className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t('report.noRoom')}</SelectItem>
                    {rooms.map((candidate) => (
                      <SelectItem key={candidate.id} value={candidate.id}>
                        {candidate.number}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {!chosenRoom && rooms && (
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-location`}>{t('report.location')}</Label>
                <Input
                  id={`${ids}-location`}
                  name="location"
                  value={location}
                  placeholder={t('report.locationPlaceholder')}
                  onChange={(event) => setLocation(event.target.value)}
                  className="h-11"
                />
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor={`${ids}-title`}>{t('report.what')}</Label>
              <Input
                id={`${ids}-title`}
                name="title"
                value={title}
                maxLength={200}
                placeholder={t('report.whatPlaceholder')}
                aria-invalid={titleError || undefined}
                aria-describedby={titleError ? `${ids}-title-error` : undefined}
                onChange={(event) => {
                  setTitle(event.target.value)
                  setTitleError(false)
                }}
                className="h-11 text-[15px]"
              />
              {titleError && (
                <p id={`${ids}-title-error`} className="text-[13px] font-semibold text-danger-ink">
                  {t('report.titleRequired')}
                </p>
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${ids}-details`}>{t('report.details')}</Label>
              <Textarea
                id={`${ids}-details`}
                name="description"
                rows={3}
                value={description}
                placeholder={t('report.detailsPlaceholder')}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <input
                id={`${ids}-photos`}
                name="photos"
                type="file"
                accept="image/*"
                capture="environment"
                multiple
                disabled={photos.length >= MAX_PHOTOS}
                className="peer sr-only"
                aria-describedby={`${ids}-photos-hint`}
                onChange={(event) => {
                  addPhotos(event.target.files)
                  event.target.value = ''
                }}
              />
              <label
                htmlFor={`${ids}-photos`}
                className="flex h-14 cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border-strong bg-surface-2 text-[15px] font-semibold text-fg transition-colors hover:bg-surface-3 peer-focus-visible:ring-2 peer-focus-visible:ring-accent/55 peer-disabled:cursor-not-allowed peer-disabled:opacity-50"
              >
                <ImagePlus aria-hidden className="size-5" />
                {t('report.photos')}
              </label>
              <p id={`${ids}-photos-hint`} className="text-[13px] text-muted">
                {t('report.photosHint')}
              </p>
              {photos.length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {photos.map((photo, index) => (
                    <li key={`${photo.name}-${index}`} className="relative">
                      {previews[index] ? (
                        <img src={previews[index] ?? ''} alt={photo.name} className="size-16 rounded-lg object-cover" />
                      ) : (
                        <span className="grid size-16 place-items-center rounded-lg bg-surface-2 p-1 text-center text-[11px] break-all text-muted">
                          {photo.name}
                        </span>
                      )}
                      <button
                        type="button"
                        aria-label={t('report.removePhoto', { name: photo.name })}
                        onClick={() => setPhotos((current) => current.filter((_, i) => i !== index))}
                        className="absolute -top-1.5 -right-1.5 grid size-6 place-items-center rounded-full border border-border bg-surface text-muted shadow-xs hover:text-fg"
                      >
                        <X aria-hidden className="size-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="grid gap-1.5">
              <span id={`${ids}-priority`} className="text-[13px] font-semibold text-fg">
                {t('report.priority')}
              </span>
              <ToggleGroup
                type="single"
                aria-labelledby={`${ids}-priority`}
                value={priority}
                onValueChange={(value) => value && setPriority(value as Priority)}
                className="grid grid-cols-4"
              >
                {PRIORITIES.map((value) => (
                  <ToggleGroupItem key={value} value={value} className="h-9">
                    {t(`priorities.${value}`)}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>
            {technicians && technicians.length > 0 && (
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-assignee`}>{t('report.assignee')}</Label>
                <Select name="assigned_to_id" value={assigneeId} onValueChange={setAssigneeId}>
                  <SelectTrigger id={`${ids}-assignee`} className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t('report.unassigned')}</SelectItem>
                    {technicians.map((person) => (
                      <SelectItem key={person.id} value={person.id}>
                        {person.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {chosenRoom && (
              <div className="grid gap-3 rounded-xl border border-border p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <Label htmlFor={`${ids}-blocks`} className="text-[15px]">
                      {t('report.blocks')}
                    </Label>
                    <p className="mt-0.5 text-[13px] text-muted">{t('report.blocksHint')}</p>
                  </div>
                  <Switch id={`${ids}-blocks`} name="blocks_room" checked={blocksRoom} onCheckedChange={setBlocksRoom} />
                </div>
                {blocksRoom && (
                  <div className="grid gap-1.5">
                    <Label htmlFor={`${ids}-until`}>{t('report.until')}</Label>
                    <DatePicker id={`${ids}-until`} value={until} onChange={setUntil} min={nextDay(businessDate) ?? undefined} />
                    <p className="text-[13px] text-muted">{t('report.untilHint')}</p>
                  </div>
                )}
              </div>
            )}
            {report.isError && (
              <div role="alert" className="grid gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
                <p className="flex gap-2">
                  <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                  {errorMessage(report.error, t)}
                </p>
                {needsForce && canForce && (
                  <div className="grid gap-2">
                    <p className="text-[13px]">{t('report.forceHint')}</p>
                    <Button variant="danger" size="sm" className="justify-self-start" onClick={() => send(true)} loading={report.isPending}>
                      {t('report.force')}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </SheetBody>
          <SheetFooter>
            <Button type="submit" variant="primary" className="h-12 w-full rounded-xl text-[15px] sm:w-auto sm:px-6" loading={report.isPending}>
              {t('report.submit')}
            </Button>
          </SheetFooter>
        </form>
  )
}
