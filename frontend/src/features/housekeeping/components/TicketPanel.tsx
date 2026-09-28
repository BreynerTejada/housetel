import { addDays, format, isValid, parseISO } from 'date-fns'
import { Check, ImagePlus, Play, Trash, TriangleAlert } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DatePicker } from '@/components/DatePicker'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatRelative, normalizeLang } from '@/lib/format'
import {
  addTicketPhoto,
  cancelTicket,
  deleteTicket,
  resolveTicket,
  startTicket,
  updateTicket,
  useHkMutation,
  type MaintenanceTicket,
  type Technician,
  type TicketStatus,
} from '../api'
import { PrivatePhoto } from './PrivatePhoto'
import { PriorityBadge } from './TaskBadges'

const NOBODY = 'nobody'
const TONE: Record<TicketStatus, 'warning' | 'info' | 'success' | 'stone'> = {
  open: 'warning',
  in_progress: 'info',
  resolved: 'success',
  cancelled: 'stone',
}

export interface TicketPermissions {
  /** `housekeeping.maintenance` or supervise: work the ticket. */
  repair: boolean
  /** `housekeeping.supervise`: delete. */
  supervise: boolean
}

function nextDay(date: string): string | null {
  const day = parseISO(date)
  return isValid(day) ? format(addDays(day, 1), 'yyyy-MM-dd') : null
}

/** One damage report: details, private photos and — for maintenance — assign, block, start, resolve, cancel. */
export function TicketPanel({
  ticket,
  onOpenChange,
  can,
  technicians,
  businessDate,
  userId,
}: {
  ticket: MaintenanceTicket | null
  onOpenChange: (open: boolean) => void
  can: TicketPermissions
  technicians: Technician[]
  businessDate: string
  userId: string | undefined
}) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  if (!ticket) return <Sheet open={false} onOpenChange={onOpenChange} />
  const where = ticket.room
    ? `${t('card.room', { number: ticket.room.number })} · ${ticket.room.room_type.name[lang] || ticket.room.room_type.code}`
    : ticket.location || t('ticket.commonArea')
  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(30rem,94vw)]">
        <SheetHeader>
          <SheetTitle>{ticket.title}</SheetTitle>
          <SheetDescription>{where}</SheetDescription>
        </SheetHeader>
        <TicketBody
          key={ticket.id}
          current={ticket}
          can={can}
          technicians={technicians}
          businessDate={businessDate}
          userId={userId}
          onClose={() => onOpenChange(false)}
        />
      </SheetContent>
    </Sheet>
  )
}

/** The body of the panel; it remounts for each ticket, so its form starts from that ticket. */
function TicketBody({
  current,
  can,
  technicians,
  businessDate,
  userId,
  onClose,
}: {
  current: MaintenanceTicket
  can: TicketPermissions
  technicians: Technician[]
  businessDate: string
  userId: string | undefined
  onClose: () => void
}) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const [error, setError] = useState<string | null>(null)
  const [needsForce, setNeedsForce] = useState(false)
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')
  const [blocks, setBlocks] = useState(current.blocks_room)
  const [until, setUntil] = useState<string | null>(current.blocked_until ?? nextDay(businessDate))

  const act = useHkMutation((run: () => Promise<unknown>) => run(), {
    onSuccess: () => {
      setError(null)
      setNeedsForce(false)
    },
    onError: (issue) => {
      setError(errorMessage(issue, t))
      setNeedsForce(isApiError(issue) && issue.code === 'room_has_reservations')
    },
  })
  const cancel = useHkMutation((id: string) => cancelTicket(id, reason.trim()), {
    onSuccess: () => toast.success(t('ticket.cancelled')),
  })
  const remove = useHkMutation((id: string) => deleteTicket(id), {
    onSuccess: () => {
      toast.success(t('ticket.deleted'))
      onClose()
    },
  })

  const open = current.status === 'open' || current.status === 'in_progress'
  const mayAddPhotos = open && (can.repair || current.reported_by?.id === userId)

  function saveBlock(force = false) {
    act.mutate(() =>
      updateTicket(current.id, { blocks_room: blocks, blocked_until: blocks ? until : null, force: force || undefined }).then(() =>
        toast.success(t('ticket.blockSaved')),
      ),
    )
  }

  return (
        <SheetBody className="grid content-start gap-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONE[current.status]}>{t(`maintenance.status.${current.status}`)}</Badge>
            <PriorityBadge priority={current.priority} />
          </div>

          <div className="grid gap-2 text-sm">
            <p className="whitespace-pre-line text-fg">{current.description || t('ticket.noDescription')}</p>
            <p className="text-[13px] text-muted">
              {current.reported_by
                ? t('maintenance.reportedBy', { name: current.reported_by.full_name, when: formatRelative(current.created_at, lang) })
                : t('maintenance.reported', { when: formatRelative(current.created_at, lang) })}
            </p>
            {current.status === 'in_progress' && current.started_at && (
              <p className="text-[13px] text-muted">{t('ticket.startedAt', { when: formatRelative(current.started_at, lang) })}</p>
            )}
            {current.block && !current.block.released_at && (
              <p className="hatch rounded-md bg-room-ooo-soft px-2.5 py-1.5 text-[13px] font-semibold text-stone-ink">
                {t('ticket.blockedFrom', {
                  start: formatDate(current.block.start_date, 'd MMM', lang),
                  end: formatDate(current.block.end_date, 'd MMM', lang),
                })}
              </p>
            )}
            {current.status === 'resolved' && (
              <div className="rounded-lg bg-success-soft px-3 py-2 text-[13px] text-success-ink">
                <p className="font-semibold">
                  {t('ticket.resolvedBy', {
                    name: current.resolved_by?.full_name ?? '—',
                    when: formatRelative(current.resolved_at, lang),
                  })}
                </p>
                {current.resolution_notes && <p className="mt-1 whitespace-pre-line">{current.resolution_notes}</p>}
              </div>
            )}
          </div>

          {(current.photos.length > 0 || mayAddPhotos) && (
            <div className="grid gap-2">
              <ul className="grid grid-cols-2 gap-2">
                {current.photos.map((photo, index) => (
                  <li key={photo.id}>
                    <PrivatePhoto photo={photo} alt={t('ticket.photo', { index: index + 1 })} />
                  </li>
                ))}
              </ul>
              {mayAddPhotos && current.photos.length < 6 && (
                <>
                  <input
                    id={`${ids}-photo`}
                    type="file"
                    name="image"
                    accept="image/*"
                    capture="environment"
                    className="peer sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      event.target.value = ''
                      if (file) act.mutate(() => addTicketPhoto(current.id, file).then(() => toast.success(t('ticket.photoAdded'))))
                    }}
                  />
                  <label
                    htmlFor={`${ids}-photo`}
                    className="inline-flex h-9 cursor-pointer items-center gap-2 justify-self-start rounded-md border border-border bg-surface px-3 text-sm font-semibold text-fg shadow-xs hover:bg-surface-2 peer-focus-visible:ring-2 peer-focus-visible:ring-accent/55"
                  >
                    <ImagePlus aria-hidden className="size-4" />
                    {t('ticket.addPhoto')}
                  </label>
                </>
              )}
            </div>
          )}

          {error && (
            <div role="alert" className="grid gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
              <p className="flex gap-2">
                <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                {error}
              </p>
              {needsForce && can.repair && (
                <Button variant="danger" size="sm" className="justify-self-start" onClick={() => saveBlock(true)}>
                  {t('report.force')}
                </Button>
              )}
            </div>
          )}

          {can.repair && open && (
            <div className="grid gap-5">
              <div className="grid gap-1.5">
                <Label htmlFor={`${ids}-assignee`}>{t('ticket.assignee')}</Label>
                <Select
                  name="assigned_to"
                  value={current.assigned_to?.id ?? NOBODY}
                  onValueChange={(value) =>
                    act.mutate(() =>
                      updateTicket(current.id, { assigned_to_id: value === NOBODY ? null : value }).then(() => toast.success(t('ticket.assigned'))),
                    )
                  }
                >
                  <SelectTrigger id={`${ids}-assignee`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NOBODY}>{t('ticket.nobody')}</SelectItem>
                    {technicians.map((person) => (
                      <SelectItem key={person.id} value={person.id}>
                        {person.full_name}
                      </SelectItem>
                    ))}
                    {current.assigned_to && !technicians.some((person) => person.id === current.assigned_to?.id) && (
                      <SelectItem value={current.assigned_to.id}>{current.assigned_to.full_name}</SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              {current.room && (
                <div className="grid gap-3 rounded-xl border border-border p-4">
                  <div className="flex items-center justify-between gap-4">
                    <Label htmlFor={`${ids}-blocks`}>{t('ticket.block')}</Label>
                    <Switch id={`${ids}-blocks`} name="blocks_room" checked={blocks} onCheckedChange={setBlocks} />
                  </div>
                  {blocks && (
                    <div className="grid gap-1.5">
                      <Label htmlFor={`${ids}-until`}>{t('ticket.blockUntil')}</Label>
                      <DatePicker id={`${ids}-until`} value={until} onChange={setUntil} min={nextDay(businessDate) ?? undefined} />
                    </div>
                  )}
                  {(blocks !== current.blocks_room || (blocks && until !== current.blocked_until)) && (
                    <Button size="sm" className="justify-self-start" loading={act.isPending} onClick={() => saveBlock()}>
                      {t('ticket.saveBlock')}
                    </Button>
                  )}
                </div>
              )}

              {current.status === 'open' && (
                <Button
                  className="justify-self-start"
                  loading={act.isPending}
                  onClick={() => act.mutate(() => startTicket(current.id).then(() => toast.success(t('ticket.started', { title: current.title }))))}
                >
                  <Play aria-hidden />
                  {t('ticket.start')}
                </Button>
              )}

              <div className="grid gap-2 rounded-xl bg-surface-2 p-4">
                <Label htmlFor={`${ids}-notes`}>{t('ticket.resolutionLabel')}</Label>
                <Textarea
                  id={`${ids}-notes`}
                  name="resolution_notes"
                  rows={2}
                  value={notes}
                  placeholder={t('ticket.resolutionPlaceholder')}
                  onChange={(event) => setNotes(event.target.value)}
                  className="bg-surface"
                />
                <p className="text-[13px] text-muted">{t('ticket.resolveHint')}</p>
                <Button
                  variant="primary"
                  className="justify-self-start"
                  loading={act.isPending}
                  onClick={() => act.mutate(() => resolveTicket(current.id, notes.trim()).then(() => toast.success(t('ticket.resolved'))))}
                >
                  <Check aria-hidden />
                  {t('ticket.resolve')}
                </Button>
              </div>

              <div className="flex flex-wrap gap-2">
                <ConfirmDialog
                  trigger={
                    <Button variant="ghost" size="sm" className="text-muted">
                      {t('ticket.cancel')}
                    </Button>
                  }
                  title={t('ticket.cancelTitle')}
                  description={t('ticket.cancelDescription')}
                  confirmLabel={t('ticket.cancel')}
                  onConfirm={() => cancel.mutateAsync(current.id)}
                >
                  <div className="grid gap-1.5">
                    <Label htmlFor={`${ids}-reason`}>{t('ticket.cancelReason')}</Label>
                    <Textarea id={`${ids}-reason`} name="reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
                  </div>
                </ConfirmDialog>
                {can.supervise && (
                  <ConfirmDialog
                    trigger={
                      <Button variant="ghost" size="sm" className="text-danger-ink">
                        <Trash aria-hidden />
                        {t('ticket.delete')}
                      </Button>
                    }
                    title={t('ticket.deleteTitle')}
                    description={t('ticket.deleteDescription')}
                    confirmLabel={t('ticket.delete')}
                    onConfirm={() => remove.mutateAsync(current.id)}
                  />
                )}
              </div>
            </div>
          )}
        </SheetBody>
  )
}
