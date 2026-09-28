import { useQueryClient } from '@tanstack/react-query'
import { Copy, ExternalLink, Pencil } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { bookingKeys, updateReservation, useRefreshFrontDesk, type Guarantee, type ReservationDetail } from '../api'
import { tr } from '../lib/labels'

const GUARANTEES: Guarantee[] = ['none', 'card', 'deposit', 'ota']
const ETA = /^([01]\d|2[0-3]):[0-5]\d$/

/** The reservation's own data (arrival time, guarantee, policy, requests, notes, portal link), editable in place. */
export function ReservationFacts({ reservation }: { reservation: ReservationDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('bookings.manage')
  const [editing, setEditing] = useState(false)
  const policy = reservation.cancellation_policy_snapshot
  const policyText = !policy || !policy.name ? t('wizard.policy.none') : tr(policy.name, i18n.language)
  const dateTime = lang === 'en' ? 'MMM d, yyyy HH:mm' : 'd MMM yyyy, HH:mm'

  async function copyPortal() {
    try {
      await navigator.clipboard.writeText(reservation.portal_url)
      toast.success(t('facts.portalCopied'))
    } catch {
      toast.error(t('facts.portalCopyFailed'))
    }
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-xs">
      <header className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-bold">{t('facts.title')}</h2>
        {canManage && (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            <Pencil aria-hidden />
            {t('common:actions.edit')}
          </Button>
        )}
      </header>
      <dl className="grid gap-x-6 gap-y-3 text-[13px] sm:grid-cols-2">
        <Fact label={t('facts.eta')}>{reservation.eta ? reservation.eta.slice(0, 5) : t('facts.none')}</Fact>
        <Fact label={t('facts.guarantee')}>{t(`guarantees.${reservation.guarantee}`)}</Fact>
        <Fact label={t('facts.language')}>{t(`common:languages.${reservation.language}`, { defaultValue: reservation.language })}</Fact>
        <Fact label={t('facts.policy')}>{policyText}</Fact>
        {reservation.promo_code && <Fact label={t('facts.promo')}>{reservation.promo_code}</Fact>}
        {(reservation.channel_code || reservation.external_id) && (
          <Fact label={t('facts.channel')}>
            {[reservation.channel_code, reservation.external_id].filter(Boolean).join(' · ')}
          </Fact>
        )}
        {reservation.status === 'tentative' && reservation.hold_expires_at && (
          <Fact label={t('facts.hold')}>{formatDate(reservation.hold_expires_at, dateTime, lang)}</Fact>
        )}
        <Fact label={t('facts.created')}>
          {formatDate(reservation.created_at, dateTime, lang)}
          {reservation.created_by && ` · ${reservation.created_by.full_name}`}
        </Fact>
        {reservation.status === 'cancelled' && (
          <Fact label={t('facts.cancelled')}>
            {reservation.cancelled_at && formatDate(reservation.cancelled_at, dateTime, lang)}
            {reservation.cancellation_reason && ` · ${reservation.cancellation_reason}`}
            {Number(reservation.cancellation_fee) > 0 && (
              <>
                {' · '}
                <MoneyText value={reservation.cancellation_fee} currency={reservation.currency} />
              </>
            )}
          </Fact>
        )}
      </dl>
      <div className="mt-4 grid gap-3 border-t border-border pt-4 text-[13px] sm:grid-cols-2">
        <Fact label={t('facts.requests')}>{reservation.special_requests || t('facts.none')}</Fact>
        <Fact label={t('facts.notes')}>{reservation.notes || t('facts.none')}</Fact>
      </div>
      {reservation.portal_url && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <span className="text-[13px] font-semibold text-muted">{t('facts.portal')}</span>
          <Button size="sm" variant="ghost" onClick={() => void copyPortal()}>
            <Copy aria-hidden />
            {t('facts.copyPortal')}
          </Button>
          <Button asChild size="sm" variant="ghost">
            <a href={reservation.portal_url} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden />
              {t('facts.openPortal')}
            </a>
          </Button>
        </div>
      )}
      {editing && <EditFactsDialog reservation={reservation} onClose={() => setEditing(false)} />}
    </section>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 break-words whitespace-pre-line text-fg">{children}</dd>
    </div>
  )
}

function EditFactsDialog({ reservation, onClose }: { reservation: ReservationDetail; onClose: () => void }) {
  const { t } = useTranslation('frontdesk')
  const ids = { eta: useId(), guarantee: useId(), language: useId(), requests: useId(), notes: useId() }
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const [eta, setEta] = useState(reservation.eta ? reservation.eta.slice(0, 5) : '')
  const [guarantee, setGuarantee] = useState<Guarantee>(reservation.guarantee)
  const [language, setLanguage] = useState(reservation.language)
  const [requests, setRequests] = useState(reservation.special_requests)
  const [notes, setNotes] = useState(reservation.notes)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const etaValid = eta === '' || ETA.test(eta)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const detail = await updateReservation(reservation.id, {
        eta: eta || null,
        guarantee,
        language,
        special_requests: requests.trim(),
        notes: notes.trim(),
      })
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(t('facts.saved'))
      onClose()
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !saving && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('facts.editTitle')}</DialogTitle>
          <DialogDescription>{reservation.code}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="grid gap-2">
              <Label htmlFor={ids.eta}>{t('wizard.eta')}</Label>
              <Input id={ids.eta} value={eta} onChange={(event) => setEta(event.target.value.replace(/[^\d:]/g, '').slice(0, 5))} placeholder="HH:MM" aria-invalid={!etaValid} className="num" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={ids.guarantee}>{t('facts.guarantee')}</Label>
              <Select value={guarantee} onValueChange={(value) => setGuarantee(value as Guarantee)}>
                <SelectTrigger id={ids.guarantee}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GUARANTEES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`guarantees.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor={ids.language}>{t('facts.language')}</Label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger id={ids.language}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="es">{t('common:languages.es')}</SelectItem>
                  <SelectItem value="en">{t('common:languages.en')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {!etaValid && <p className="text-[13px] font-semibold text-danger-ink">{t('wizard.errors.etaInvalid')}</p>}
          <div className="grid gap-2">
            <Label htmlFor={ids.requests}>{t('facts.requests')}</Label>
            <Textarea id={ids.requests} value={requests} onChange={(event) => setRequests(event.target.value)} rows={2} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={ids.notes}>{t('facts.notes')}</Label>
            <Textarea id={ids.notes} value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} />
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={saving} disabled={!etaValid}>
            {t('common:actions.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
