import { useMutation } from '@tanstack/react-query'
import { Camera, CircleCheck, LoaderCircle } from 'lucide-react'
import { useId, useState, type ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { buttonVariants, Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { confirmDocuments, uploadDocument, type CheckinPayload, type CheckinSlot, type DocumentKind } from '../../api'
import { documentKindFor, identityDocuments, slotName } from '../../lib/checkin'
import { portalError } from '../../lib/errors'
import { StepActions, StepError } from './StepLayout'

/** Step 2 — a clear photo (or PDF) of each adult's identity document, stored privately for the hotel. */
export function DocumentsStep({
  checkin,
  token,
  onUpdated,
  onSaved,
}: {
  checkin: CheckinPayload
  token: string
  onUpdated: (payload: CheckinPayload) => void
  onSaved: (payload: CheckinPayload) => void
}) {
  const { t } = useTranslation('guestportal')
  const [missing, setMissing] = useState<string[]>([])
  const confirm = useMutation({
    mutationFn: () => confirmDocuments(token),
    onSuccess: onSaved,
    onError: (error) => {
      const ids = isApiError(error) ? (error.data?.guest_ids as string[] | undefined) : undefined
      setMissing(ids ?? [])
    },
  })
  const slots = checkin.guests.filter((slot) => slot.guest_id)

  return (
    <div className="grid gap-5">
      <p className="text-[15px] text-muted">{t('checkin.documents.lead')}</p>
      {slots.map((slot) => (
        <DocumentCard key={slot.slot} slot={slot} token={token} onUpdated={onUpdated} flagged={missing.includes(slot.guest_id!)} />
      ))}
      {confirm.isError && <StepError message={portalError(confirm.error, t)} />}
      <StepActions>
        <Button variant="primary" size="lg" className="w-full sm:w-auto" loading={confirm.isPending} onClick={() => confirm.mutate()}>
          {t('checkin.continue')}
        </Button>
      </StepActions>
    </div>
  )
}

function nextKind(slot: CheckinSlot): { kind: DocumentKind; label: 'upload' | 'back' | 'another' } {
  const documents = identityDocuments(slot)
  if (!documents.length) return { kind: documentKindFor(slot.data.document_type), label: 'upload' }
  const hasFront = documents.some((document) => document.kind === 'id_front')
  const hasBack = documents.some((document) => document.kind === 'id_back')
  if (hasFront && !hasBack && slot.data.document_type !== 'PA') return { kind: 'id_back', label: 'back' }
  return { kind: 'other', label: 'another' }
}

function DocumentCard({
  slot,
  token,
  onUpdated,
  flagged,
}: {
  slot: CheckinSlot
  token: string
  onUpdated: (payload: CheckinPayload) => void
  flagged: boolean
}) {
  const { t } = useTranslation('guestportal')
  const titleId = useId()
  const documents = identityDocuments(slot)
  const next = nextKind(slot)
  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(token, { guestId: slot.guest_id!, kind: next.kind, file }),
    onSuccess: (result) => onUpdated(result.checkin),
  })

  function pick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // the same file can be picked again after an error
    if (file) upload.mutate(file)
  }

  const missing = slot.is_adult && documents.length === 0
  return (
    <section
      aria-labelledby={titleId}
      className={cn('grid gap-3 rounded-2xl border bg-surface p-4 shadow-xs sm:p-5', flagged && missing ? 'border-danger' : 'border-border')}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id={titleId} className="text-base font-bold">
          {slotName(slot)}
        </h3>
        <span className={cn('text-[13px]', missing ? 'font-semibold text-warning-ink' : 'text-muted')}>
          {!slot.is_adult ? t('checkin.documents.minor') : missing ? t('checkin.documents.pending') : null}
        </span>
      </header>
      {documents.length > 0 && (
        <ul className="grid gap-1.5">
          {documents.map((document) => (
            <li key={document.id} className="flex items-center gap-2 text-sm font-semibold text-success-ink">
              <CircleCheck aria-hidden className="size-4 shrink-0" />
              {t('checkin.documents.received', { kind: t(`checkin.documents.kinds.${document.kind}`) })}
            </li>
          ))}
        </ul>
      )}
      <label
        className={cn(
          buttonVariants({ variant: documents.length ? 'ghost' : 'secondary', size: 'lg' }),
          'w-full cursor-pointer focus-within:ring-2 focus-within:ring-accent/55 sm:w-auto sm:justify-self-start',
          upload.isPending && 'pointer-events-none opacity-60',
        )}
      >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
          className="sr-only"
          onChange={pick}
          disabled={upload.isPending}
          aria-describedby={upload.isError ? `${titleId}-error` : undefined}
        />
        {upload.isPending ? <LoaderCircle aria-hidden className="animate-spin" /> : <Camera aria-hidden />}
        {upload.isPending ? t('checkin.documents.uploading') : t(`checkin.documents.${next.label}`)}
      </label>
      {upload.isError && (
        <p id={`${titleId}-error`} role="alert" className="text-sm font-medium text-danger-ink">
          {portalError(upload.error, t)}
        </p>
      )}
    </section>
  )
}
