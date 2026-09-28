import { useQueryClient } from '@tanstack/react-query'
import { Star, UserPlus, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import { countryName } from '@/features/guests/countries'
import { formatDocument, formatPhone } from '@/features/guests/format'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { addOccupant, bookingKeys, removeOccupant, useRefreshFrontDesk, type GuestSummaryRef, type ReservationDetail, type StayDetail } from '../api'
import { tr, unitLabel } from '../lib/labels'

/** Tab "Huéspedes": the booker and, per stay, the companions staying in it (added with GuestPicker). */
export function GuestsPanel({ reservation }: { reservation: ReservationDetail }) {
  const { t } = useTranslation('frontdesk')
  const stays = reservation.stays.filter((stay) => stay.status !== 'cancelled' && stay.status !== 'no_show')
  return (
    <div className="grid gap-5">
      <section className="grid gap-2">
        <h2 className="eyebrow">{t('guestsTab.booker')}</h2>
        <GuestCard guest={reservation.booker} />
      </section>
      {stays.map((stay) => (
        <StayOccupants key={stay.id} reservation={reservation} stay={stay} />
      ))}
    </div>
  )
}

function GuestCard({ guest, onRemove }: { guest: GuestSummaryRef; onRemove?: () => void }) {
  const { t, i18n } = useTranslation('frontdesk')
  const facts = [
    formatDocument(guest.document_type, guest.document_number),
    guest.nationality ? countryName(guest.nationality, i18n.language) : '',
    guest.email,
    formatPhone(guest.phone),
  ].filter(Boolean)
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5 font-semibold text-fg">
          {guest.full_name}
          {guest.is_vip && <Star role="img" aria-label={t('vip')} className="size-3.5 fill-warning text-warning" />}
          {guest.is_foreign_non_resident && <Badge tone="info">{t('guestsTab.foreign')}</Badge>}
        </p>
        {facts.length > 0 ? (
          <ul className="mt-0.5 flex flex-wrap gap-x-3 text-[13px] text-muted">
            {facts.map((fact) => (
              <li key={fact} className="num">
                {fact}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-warning-ink">{t('guestsTab.noData')}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/app/guests/${guest.id}`}>{t('guestsTab.profile')}</Link>
        </Button>
        {onRemove && (
          <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={t('guestsTab.remove', { name: guest.full_name })}>
            <X aria-hidden />
          </Button>
        )}
      </div>
    </div>
  )
}

function StayOccupants({ reservation, stay }: { reservation: ReservationDetail; stay: StayDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  const canManage = useCan('bookings.manage')
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const [adding, setAdding] = useState(false)
  const [guest, setGuest] = useState<GuestPickerValue | null>(null)
  const [saving, setSaving] = useState(false)
  const unit = unitLabel(stay.room?.number, stay.bed?.label)
  const editable = canManage && stay.status !== 'checked_out'

  async function run(action: () => Promise<ReservationDetail>, message: string) {
    setSaving(true)
    try {
      const detail = await action()
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(message)
      setAdding(false)
      setGuest(null)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="grid gap-2">
      <h2 className="eyebrow">
        {t('guestsTab.stay', { type: tr(stay.room_type.name, i18n.language) })}
        {unit && ` · ${t('checkout.room', { room: unit })}`}
      </h2>
      {stay.occupants.length === 0 && !adding && <p className="text-[13px] text-muted">{t('guestsTab.noCompanions')}</p>}
      {stay.occupants.map((occupant) => (
        <GuestCard
          key={occupant.id}
          guest={occupant}
          onRemove={editable ? () => void run(() => removeOccupant(stay.id, occupant.id), t('guestsTab.removed', { name: occupant.full_name })) : undefined}
        />
      ))}
      {editable &&
        (adding ? (
          <div className="grid gap-3 rounded-lg border border-dashed border-border-strong p-3">
            <GuestPicker value={guest} onChange={setGuest} autoFocus />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setAdding(false)} disabled={saving}>
                {t('common:actions.cancel')}
              </Button>
              <Button
                size="sm"
                variant="primary"
                disabled={!guest}
                loading={saving}
                onClick={() =>
                  guest &&
                  void run(
                    () => addOccupant(stay.id, isExistingGuest(guest) ? { guest_id: guest.id } : { guest }),
                    t('guestsTab.added'),
                  )
                }
              >
                {t('guestsTab.addToStay')}
              </Button>
            </div>
          </div>
        ) : (
          <Button size="sm" className="justify-self-start" onClick={() => setAdding(true)}>
            <UserPlus aria-hidden />
            {t('guestsTab.addCompanion')}
          </Button>
        ))}
    </section>
  )
}
