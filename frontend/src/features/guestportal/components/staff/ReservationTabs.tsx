import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleDashed, FileText, QrCode, ShieldCheck, X } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { countryName } from '@/features/guests/countries'
import { usePrivateFileUrl } from '@/features/guests/hooks'
import { errorMessage } from '@/lib/errors'
import { useActiveProperty } from '@/lib/auth'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  approveRequest,
  getCatalogExtras,
  getReservationCheckin,
  getServiceRequests,
  portalKeys,
  rejectRequest,
  completeRequest,
  type CheckinStatus,
  type MissingItem,
  type RequestStatus,
  type StaffCheckin,
  type StaffDocument,
  type StaffServiceRequest,
  type StaffSlot,
} from '../../api'
import { moneyLabel } from '../../lib/money'
import { formatHotelDateTime, tr } from '../../lib/text'

const STATUS_TONE: Record<CheckinStatus, BadgeTone> = { not_started: 'neutral', in_progress: 'warning', completed: 'success' }
const REQUEST_TONE: Record<RequestStatus, BadgeTone> = { requested: 'warning', approved: 'success', rejected: 'stone', done: 'info' }

// ---- Check-in online tab --------------------------------------------------------------------------

/** Reservation tab "Check-in online": what the guest registered, their ID photos and the signature. */
export function CheckinTab({ reservationId }: { reservationId: string }) {
  const checkin = useQuery({ queryKey: portalKeys.reservationCheckin(reservationId), queryFn: () => getReservationCheckin(reservationId) })
  if (checkin.isPending) return <LoadingState variant="rows" rows={4} />
  if (checkin.isError) return <ErrorState error={checkin.error} onRetry={() => checkin.refetch()} />
  return <CheckinDetail checkin={checkin.data} />
}

function guestName(slot: StaffSlot): string {
  return 'full_name' in slot.data ? slot.data.full_name : ''
}

function useHotelTimeZone(): string {
  return useActiveProperty().property?.timezone ?? 'America/Bogota'
}

function CheckinDetail({ checkin }: { checkin: StaffCheckin }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const timeZone = useHotelTimeZone()
  const booker = checkin.guests.find((slot) => slot.role === 'booker')
  const notStarted = checkin.status === 'not_started'

  return (
    <div className="grid gap-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Badge tone={STATUS_TONE[checkin.status]}>{t(`staff.status.${checkin.status}`)}</Badge>
        <span className="text-[13px] text-muted">
          {checkin.status === 'completed' && checkin.completed_at
            ? t('staff.completedAt', { date: formatHotelDateTime(checkin.completed_at, timeZone, lang) })
            : checkin.status === 'in_progress'
              ? t('staff.step', { step: t(`checkin.steps.${checkin.current_step}`) })
              : null}
        </span>
        <span className="ml-auto text-[13px]">
          <span className="text-muted">{t('staff.eta')}: </span>
          <span className="font-semibold">{checkin.eta ?? t('staff.noEta')}</span>
        </span>
      </header>

      {notStarted && (
        <EmptyState
          icon={QrCode}
          title={t('staff.notStarted')}
          description={checkin.window.is_open ? t('staff.notStartedHint') : t('staff.windowOpens', { date: formatDate(checkin.window.opens_on, undefined, lang) })}
          className="rounded-xl border border-dashed border-border py-8"
        />
      )}

      {checkin.status !== 'completed' && checkin.missing.length > 0 && <MissingList missing={checkin.missing} guests={checkin.guests} />}

      {!notStarted && checkin.guests.map((slot) => <GuestPanel key={slot.slot} slot={slot} lang={lang} />)}

      {checkin.signature_url && (
        <SignaturePanel url={checkin.signature_url} name={booker ? guestName(booker) : ''} checkin={checkin} lang={lang} timeZone={timeZone} />
      )}

      {checkin.retention_purged_at && (
        <p className="flex items-start gap-2 rounded-xl border border-border bg-surface-2 px-4 py-3 text-[13px] text-muted">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-success-ink" />
          <span>
            {t('staff.retentionPurged', { date: formatHotelDateTime(checkin.retention_purged_at, timeZone, lang) })}{' '}
            <Link to="/legal/privacidad" className="font-semibold text-accent-ink underline-offset-4 hover:underline">
              {t('staff.retentionPolicy')}
            </Link>
          </span>
        </p>
      )}
    </div>
  )
}

function MissingList({ missing, guests }: { missing: MissingItem[]; guests: StaffSlot[] }) {
  const { t } = useTranslation('guestportal')
  const id = useId()
  const nameOf = (guestId?: string | null) => {
    const slot = guests.find((item) => item.guest_id === guestId)
    return slot ? guestName(slot) : ''
  }
  return (
    <div className="rounded-xl bg-warning-soft px-4 py-3 text-warning-ink">
      <p id={id} className="text-[13px] font-bold">
        {t('staff.missing')}
      </p>
      <ul aria-labelledby={id} className="mt-1 grid gap-0.5 text-sm">
        {missing.map((item, index) => (
          <li key={`${item.code}-${index}`} className="flex items-center gap-2">
            <CircleDashed aria-hidden className="size-3.5 shrink-0" />
            {t(`staff.missingItems.${item.code}`, { name: nameOf(item.guest_id) })}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="truncate font-medium">{children}</dd>
    </div>
  )
}

function GuestPanel({ slot, lang }: { slot: StaffSlot; lang: 'es' | 'en' }) {
  const { t } = useTranslation('guestportal')
  const titleId = useId()
  const data = 'full_name' in slot.data ? slot.data : null
  const name = data?.full_name || t('staff.noData')
  const travel = slot.travel
  const residence = data ? [data.city_of_residence, countryName(data.country_of_residence, lang)].filter(Boolean).join(', ') : ''

  return (
    <section aria-labelledby={titleId} className="grid gap-3 rounded-xl border border-border bg-surface p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h3 id={titleId} className="text-[15px] font-bold">
          {name}
        </h3>
        <Badge tone={slot.role === 'booker' ? 'accent' : 'neutral'}>{slot.role === 'booker' ? t('staff.booker') : t('staff.companion')}</Badge>
        {!slot.is_adult && <Badge tone="info">{t('staff.minor')}</Badge>}
        <span className={cn('ml-auto text-[12px] font-semibold', slot.complete ? 'text-success-ink' : 'text-warning-ink')}>
          {slot.complete ? t('staff.complete') : t('staff.incomplete')}
        </span>
      </header>
      {data && (
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <Item label={t('staff.document')}>{[data.document_type, data.document_number].filter(Boolean).join(' ') || '—'}</Item>
          <Item label={t('fields.nationality')}>{countryName(data.nationality, lang) || '—'}</Item>
          <Item label={t('staff.residence')}>{residence || '—'}</Item>
          <Item label={t('staff.birthDate')}>{data.birth_date ? formatDate(data.birth_date, undefined, lang) : '—'}</Item>
          {(data.email || data.phone) && <Item label={t('staff.contact')}>{[data.email, data.phone].filter(Boolean).join(' · ')}</Item>}
          {travel.travel_reason && (
            <Item label={t('staff.trip')}>
              {t('staff.tripLine', {
                reason: t(`travelReasons.${travel.travel_reason}`, { defaultValue: travel.travel_reason }),
                origin: travel.origin || '—',
                destination: travel.destination || '—',
              })}
            </Item>
          )}
        </dl>
      )}
      {slot.is_adult && (
        <div className="grid gap-2">
          <p className="text-[12px] text-muted">{t('staff.documents')}</p>
          {slot.documents.length ? (
            <ul className="flex flex-wrap gap-3">
              {slot.documents.map((document) => (
                <li key={document.id}>
                  <DocumentThumb document={document} name={name} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-warning-ink">{t('staff.noDocuments')}</p>
          )}
        </div>
      )}
    </section>
  )
}

/** A private ID photo (fetched with the session; never a /media URL). PDFs open in a new tab. */
function DocumentThumb({ document, name }: { document: StaffDocument; name: string }) {
  const { t } = useTranslation('guestportal')
  const file = usePrivateFileUrl(document.file_url)
  const kind = t(`checkin.documents.kinds.${document.kind}`, { defaultValue: t('checkin.documents.kinds.other') })
  const label = t('staff.documentAlt', { kind, name })
  if (file.isLoading) return <span className="grid h-24 w-36 place-items-center rounded-lg bg-surface-2 text-xs text-muted">{t('staff.loadingFile')}</span>
  if (file.isError || !file.url) return <span className="grid h-24 w-36 place-items-center rounded-lg bg-danger-soft px-2 text-center text-xs text-danger-ink">{t('staff.fileError')}</span>
  const isPdf = file.blob?.type === 'application/pdf'
  return (
    <a
      href={file.url}
      target="_blank"
      rel="noreferrer"
      title={t('staff.openDocument', { kind })}
      className="block overflow-hidden rounded-lg border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
    >
      {isPdf ? (
        <span className="flex h-24 w-36 flex-col items-center justify-center gap-1 bg-surface-2 text-xs text-muted" aria-label={label}>
          <FileText aria-hidden className="size-6" />
          {t('staff.pdf')}
        </span>
      ) : (
        <img src={file.url} alt={label} className="h-24 w-36 object-cover" />
      )}
    </a>
  )
}

function SignaturePanel({ url, name, checkin, lang, timeZone }: { url: string; name: string; checkin: StaffCheckin; lang: 'es' | 'en'; timeZone: string }) {
  const { t } = useTranslation('guestportal')
  const file = usePrivateFileUrl(url)
  return (
    <figure className="grid gap-2 rounded-xl border border-border bg-surface p-4">
      <p className="text-[12px] text-muted">{t('staff.signature')}</p>
      <div className="grid h-32 place-items-center overflow-hidden rounded-lg border border-border bg-white">
        {file.url ? <img src={file.url} alt={t('staff.signatureAlt', { name })} className="max-h-full" /> : <span className="text-xs text-[#6e675e]">{t('staff.loadingFile')}</span>}
      </div>
      {checkin.accepted_terms_at && (
        <figcaption className="text-[12px] text-muted">
          {t('staff.evidence', { date: formatHotelDateTime(checkin.accepted_terms_at, timeZone, lang), ip: checkin.ip ?? '—' })}
          {checkin.user_agent && (
            <span className="block truncate" title={checkin.user_agent}>
              {t('staff.device')}: {checkin.user_agent}
            </span>
          )}
        </figcaption>
      )}
    </figure>
  )
}

// ---- Requests tab ---------------------------------------------------------------------------------

/** Reservation tab "Solicitudes": what the guest asked from the portal, and the staff's decisions. */
export function RequestsTab({ reservationId }: { reservationId: string }) {
  const { t } = useTranslation('guestportal')
  const filters = { reservation: reservationId, page_size: 100 }
  const requests = useQuery({ queryKey: portalKeys.requests(filters), queryFn: () => getServiceRequests(filters) })
  if (requests.isPending) return <LoadingState variant="rows" rows={3} />
  if (requests.isError) return <ErrorState error={requests.error} onRetry={() => requests.refetch()} />
  if (!requests.data.results.length) return <EmptyState title={t('staff.requests.empty')} className="py-10" />
  return (
    <ul className="grid gap-3">
      {requests.data.results.map((request) => (
        <RequestRow key={request.id} request={request} />
      ))}
    </ul>
  )
}

function RequestRow({ request }: { request: StaffServiceRequest }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('guestportal.manage')
  const queryClient = useQueryClient()
  const titleId = useId()
  const [dialog, setDialog] = useState<'approve' | 'reject' | null>(null)
  const complete = useMutation({
    mutationFn: () => completeRequest(request.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: portalKeys.staff })
      toast.success(t('staff.requests.completed'))
    },
  })
  const kind = request.extra ? tr(request.extra.name, lang) : t(`staff.kinds.${request.kind}`)
  const when =
    request.requested_time &&
    (request.kind === 'late_checkout'
      ? t('staff.requests.until', { time: request.requested_time })
      : t('staff.requests.from', { time: request.requested_time }))

  return (
    <li aria-labelledby={titleId} className="grid gap-2 rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p id={titleId} className="font-bold">
          {kind}
          {request.extra && ` × ${request.quantity}`}
        </p>
        {when && <span className="text-sm text-muted">{when}</span>}
        <Badge tone={REQUEST_TONE[request.status]} className="ml-auto">
          {t(`staff.statuses.${request.status}`)}
        </Badge>
      </div>
      {request.notes && <p className="text-sm">{request.notes}</p>}
      <p className="flex flex-wrap gap-x-3 text-[12px] text-muted">
        <span>{t('staff.requests.requestedAt', { date: formatDate(request.created_at, undefined, lang) })}</span>
        {request.price && <span>{t('staff.requests.price', { amount: moneyLabel(request.price) })}</span>}
        {request.decision_note && <span>“{request.decision_note}”</span>}
      </p>
      {canManage && request.status === 'requested' && (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button size="sm" variant="primary" onClick={() => setDialog('approve')}>
            <Check aria-hidden />
            {t('staff.requests.approve')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDialog('reject')}>
            <X aria-hidden />
            {t('staff.requests.reject')}
          </Button>
        </div>
      )}
      {canManage && request.status === 'approved' && (
        <div className="pt-1">
          <Button size="sm" loading={complete.isPending} onClick={() => complete.mutate()}>
            {t('staff.requests.complete')}
          </Button>
        </div>
      )}
      {dialog === 'approve' && <ApproveDialog request={request} kind={kind} onClose={() => setDialog(null)} />}
      {dialog === 'reject' && <RejectDialog request={request} kind={kind} onClose={() => setDialog(null)} />}
    </li>
  )
}

const NO_CHARGE = '__none__'

function ApproveDialog({ request, kind, onClose }: { request: StaffServiceRequest; kind: string; onClose: () => void }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const extras = useQuery({ queryKey: portalKeys.extras, queryFn: getCatalogExtras, enabled: !request.extra, retry: false })
  const [extraId, setExtraId] = useState(request.extra?.id ?? NO_CHARGE)
  const [quantity, setQuantity] = useState(String(request.quantity || 1))
  const [note, setNote] = useState('')
  const approve = useMutation({
    mutationFn: () =>
      approveRequest(request.id, {
        ...(extraId !== NO_CHARGE && !request.extra ? { extra_id: extraId } : {}),
        ...(extraId !== NO_CHARGE ? { quantity: Math.max(1, Number(quantity) || 1) } : {}),
        note: note.trim(),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: portalKeys.staff })
      toast.success(t('staff.requests.approved'))
      onClose()
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('staff.requests.approveTitle', { kind })}</DialogTitle>
          <DialogDescription>{t('staff.requests.approveDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          {!request.extra && (
            <div className="grid gap-1.5">
              <Label htmlFor="approve-extra">{t('staff.requests.charge')}</Label>
              <Select name="extra_id" value={extraId} onValueChange={setExtraId}>
                <SelectTrigger id="approve-extra">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CHARGE}>{t('staff.requests.noCharge')}</SelectItem>
                  {(extras.data?.results ?? []).map((extra) => (
                    <SelectItem key={extra.id} value={extra.id}>
                      {tr(extra.name, lang)} · {moneyLabel(extra.price)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {extraId !== NO_CHARGE && (
            <div className="grid gap-1.5 sm:max-w-32">
              <Label htmlFor="approve-quantity">{t('staff.requests.quantity')}</Label>
              <Input id="approve-quantity" name="quantity" type="number" min={1} max={99} value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="approve-note">{t('staff.requests.note')}</Label>
            <Textarea id="approve-note" name="note" value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} />
          </div>
          {approve.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {errorMessage(approve.error, t)}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" loading={approve.isPending} onClick={() => approve.mutate()}>
            {t('staff.requests.approve')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RejectDialog({ request, kind, onClose }: { request: StaffServiceRequest; kind: string; onClose: () => void }) {
  const { t } = useTranslation('guestportal')
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const reject = useMutation({
    mutationFn: () => rejectRequest(request.id, reason.trim()),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: portalKeys.staff })
      toast.success(t('staff.requests.rejected'))
      onClose()
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('staff.requests.rejectTitle', { kind })}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label htmlFor="reject-reason">{t('staff.requests.reason')}</Label>
          <Textarea id="reject-reason" name="reason" value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
        </div>
        {reject.isError && (
          <p role="alert" className="text-sm font-medium text-danger-ink">
            {errorMessage(reject.error, t)}
          </p>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="danger" loading={reject.isPending} onClick={() => reject.mutate()}>
            {t('staff.requests.reject')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
