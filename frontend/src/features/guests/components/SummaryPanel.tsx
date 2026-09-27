import { CalendarCheck2, CalendarClock, Mail, MapPin, Phone, ShieldCheck, ShieldOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useUpdateGuest, type Guest, type StayRef } from '../api'
import { countryName } from '../countries'
import { formatPhone } from '../format'

export function SummaryPanel({ guest, readOnly }: { guest: Guest; readOnly: boolean }) {
  const { t } = useTranslation('guests')
  const { stats } = guest
  const secondary = [
    stats.cancellations ? t('detail.stats.cancellations', { count: stats.cancellations }) : null,
    stats.no_shows ? t('detail.stats.noShows', { count: stats.no_shows }) : null,
  ].filter(Boolean)

  return (
    <div className="grid gap-5">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t('detail.stats.stays')} value={stats.stays_count} note={secondary.join(' · ') || undefined} />
        <Stat label={t('detail.stats.nights')} value={stats.nights} />
        <Stat
          label={t('detail.stats.spent')}
          value={<MoneyText value={stats.total_spent} />}
          hint={t('detail.stats.spentHint')}
        />
        {stats.next_stay ? (
          <StayStat label={t('detail.stats.nextStay')} stay={stats.next_stay} icon={CalendarClock} />
        ) : (
          <StayStat label={t('detail.stats.lastStay')} stay={stats.last_stay} icon={CalendarCheck2} />
        )}
      </dl>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <ContactCard guest={guest} />
        <ConsentCard guest={guest} readOnly={readOnly} />
      </div>
    </div>
  )
}

function Stat({ label, value, note, hint }: { label: string; value: ReactNode; note?: string; hint?: string }) {
  const body = (
    <div className="flex h-full flex-col gap-1 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <dt className="text-[13px] font-semibold text-muted">{label}</dt>
      <dd className="num text-[22px] leading-7 font-bold tracking-[-0.02em] text-fg">{value}</dd>
      {note && <dd className="text-xs text-muted">{note}</dd>}
    </div>
  )
  return hint ? (
    <Tooltip content={hint}>
      <div tabIndex={0} className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
        {body}
      </div>
    </Tooltip>
  ) : (
    body
  )
}

function StayStat({ label, stay, icon: Icon }: { label: string; stay: StayRef | null; icon: typeof CalendarClock }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="flex h-full flex-col gap-1 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <dt className="flex items-center justify-between gap-2 text-[13px] font-semibold text-muted">
        {label}
        <Icon aria-hidden className="size-4 text-subtle" />
      </dt>
      {stay ? (
        <>
          <dd className="num text-[15px] leading-6 font-bold text-fg">{formatDateRange(stay.checkin, stay.checkout, lang)}</dd>
          <dd className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span className="truncate">{stay.property_name}</span>
            <StatusBadge kind="reservation" status={stay.status} />
          </dd>
        </>
      ) : (
        <dd className="text-[15px] leading-6 font-semibold text-subtle">{t('detail.stats.none')}</dd>
      )}
    </div>
  )
}

function ContactCard({ guest }: { guest: Guest }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const place = [guest.address, guest.city_of_residence, countryName(guest.country_of_residence, lang)].filter(Boolean)
  const empty = !guest.email && !guest.phone && place.length === 0
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('detail.contact')}</CardTitle>
      </CardHeader>
      <CardContent>
        {empty ? (
          <p className="text-sm text-muted">{t('detail.noContact')}</p>
        ) : (
          <ul className="grid gap-2.5 text-sm">
            {guest.email && (
              <li className="flex items-center gap-2.5">
                <Mail aria-hidden className="size-4 shrink-0 text-subtle" />
                <a href={`mailto:${guest.email}`} className="truncate text-fg underline-offset-4 hover:underline">
                  {guest.email}
                </a>
              </li>
            )}
            {guest.phone && (
              <li className="flex items-center gap-2.5">
                <Phone aria-hidden className="size-4 shrink-0 text-subtle" />
                <a href={`tel:${guest.phone}`} className="num text-fg underline-offset-4 hover:underline">
                  {formatPhone(guest.phone)}
                </a>
              </li>
            )}
            {place.length > 0 && (
              <li className="flex items-start gap-2.5">
                <MapPin aria-hidden className="mt-0.5 size-4 shrink-0 text-subtle" />
                <span className="text-fg">{place.join(', ')}</span>
              </li>
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ConsentCard({ guest, readOnly }: { guest: Guest; readOnly: boolean }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('guests.manage') && !readOnly
  const update = useUpdateGuest(guest.id)
  const [revoking, setRevoking] = useState(false)
  const granted = guest.data_processing_consent_at

  async function save(payload: Parameters<typeof update.mutateAsync>[0], message: string) {
    try {
      await update.mutateAsync(payload)
      toast.success(message)
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('detail.consent.title')}</CardTitle>
        <CardDescription>{t('detail.consent.subtitle')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-sm font-semibold">
            {granted ? (
              <>
                <ShieldCheck aria-hidden className="size-4 text-success" />
                <span className="text-success-ink">{t('detail.consent.granted', { date: formatDate(granted, undefined, lang) })}</span>
              </>
            ) : (
              <>
                <ShieldOff aria-hidden className="size-4 text-warning" />
                <span className="text-warning-ink">{t('detail.consent.missing')}</span>
              </>
            )}
          </p>
          {canManage &&
            (granted ? (
              <Button variant="ghost" size="sm" onClick={() => setRevoking(true)}>
                {t('detail.consent.revoke')}
              </Button>
            ) : (
              <Button
                size="sm"
                loading={update.isPending}
                onClick={() => save({ data_processing_consent: true }, t('detail.consent.recorded'))}
              >
                {t('detail.consent.record')}
              </Button>
            ))}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
          <label htmlFor={`marketing-${guest.id}`} className="grid gap-0.5">
            <span className="text-[13px] font-semibold text-fg">{t('detail.consent.marketing')}</span>
            <span className="text-xs text-muted">
              {guest.marketing_consent ? t('detail.consent.marketingOn') : t('detail.consent.marketingOff')}
            </span>
          </label>
          <Switch
            id={`marketing-${guest.id}`}
            checked={guest.marketing_consent}
            disabled={!canManage || update.isPending}
            onCheckedChange={(checked) =>
              save({ marketing_consent: checked }, checked ? t('detail.consent.marketingOn') : t('detail.consent.marketingOff'))
            }
          />
        </div>
      </CardContent>
      <ConfirmDialog
        open={revoking}
        onOpenChange={setRevoking}
        title={t('detail.consent.revokeTitle')}
        description={t('detail.consent.revokeDescription')}
        confirmLabel={t('detail.consent.revoke')}
        onConfirm={async () => {
          await update.mutateAsync({ data_processing_consent: false })
          toast.success(t('detail.consent.revoked'))
        }}
      />
    </Card>
  )
}
