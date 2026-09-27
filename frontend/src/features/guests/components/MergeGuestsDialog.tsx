import { ArrowLeftRight, Merge } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useMergeGuests, type DuplicateGuest, type Guest, type GuestSummary } from '../api'
import { countryName } from '../countries'
import { formatDocument, formatPhone } from '../format'
import { GuestAvatar } from './GuestAvatar'

type Profile = GuestSummary

interface Row {
  label: string
  value: (profile: Profile) => string
  /** Filled from the duplicate when the kept profile has nothing (mirrors the backend merge). */
  fills?: boolean
}

/**
 * Compare the current guest with one of its likely duplicates, choose which profile is kept and merge.
 * The backend moves every reservation, stay, folio and document to the kept profile.
 */
export function MergeGuestsDialog({
  guest,
  candidates,
  open,
  onOpenChange,
  onMerged,
}: {
  guest: Guest
  candidates: DuplicateGuest[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onMerged: (primary: Guest) => void
}) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const merge = useMergeGuests()
  const [candidateId, setCandidateId] = useState(candidates[0]?.id ?? '')
  const [keepCurrent, setKeepCurrent] = useState(true)
  const [failure, setFailure] = useState<string | null>(null)
  const candidate = candidates.find((item) => item.id === candidateId) ?? candidates[0]
  if (!candidate) return null
  const primary: Profile = keepCurrent ? guest : candidate
  const duplicate: Profile = keepCurrent ? candidate : guest

  const rows: Row[] = [
    { label: t('fields.firstName'), value: (p) => p.first_name },
    { label: t('fields.lastName'), value: (p) => p.last_name, fills: true },
    { label: t('detail.card.document'), value: (p) => formatDocument(p.document_type, p.document_number), fills: true },
    { label: t('fields.email'), value: (p) => p.email, fills: true },
    { label: t('fields.phone'), value: (p) => formatPhone(p.phone), fills: true },
    { label: t('fields.nationality'), value: (p) => countryName(p.nationality, lang), fills: true },
    { label: t('fields.residence'), value: (p) => countryName(p.country_of_residence, lang), fills: true },
    { label: t('fields.city'), value: (p) => p.city_of_residence, fills: true },
    { label: t('detail.tags'), value: (p) => p.tags.join(', '), fills: true },
    { label: t('merge.reservations'), value: (p) => String(p.reservations_count ?? '—') },
  ]

  async function confirm() {
    setFailure(null)
    try {
      const kept = await merge.mutateAsync({ primaryId: primary.id, duplicateId: duplicate.id })
      toast.success(t('merge.done'))
      onOpenChange(false)
      onMerged(kept)
    } catch (error) {
      setFailure(errorMessage(error, t))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !merge.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-3xl" hideClose={merge.isPending}>
        <DialogHeader>
          <DialogTitle>{t('merge.title')}</DialogTitle>
          <DialogDescription>{t('merge.description')}</DialogDescription>
        </DialogHeader>

        {candidates.length > 1 && (
          <fieldset className="grid gap-2">
            <legend className="eyebrow mb-2">{t('merge.candidate')}</legend>
            <RadioGroup value={candidate.id} onValueChange={setCandidateId} className="grid gap-2 sm:grid-cols-2">
              {candidates.map((item) => (
                <label
                  key={item.id}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border border-border p-2.5 transition-colors hover:bg-surface-2',
                    item.id === candidate.id && 'border-accent/50 bg-accent-soft/40',
                  )}
                >
                  <RadioGroupItem value={item.id} aria-label={item.full_name} />
                  <GuestAvatar name={item.full_name} vip={item.is_vip} size="sm" />
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-semibold text-fg">{item.full_name}</span>
                    <span className="flex flex-wrap gap-1 pt-0.5">
                      {item.reasons.map((reason) => (
                        <Badge key={reason} tone="warning">
                          {t(`reasons.${reason}`)}
                        </Badge>
                      ))}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          </fieldset>
        )}

        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-left text-[13px]">
            <thead className="bg-surface-2">
              <tr>
                <th scope="col" className="w-36 px-3 py-2.5 font-semibold text-muted">
                  {t('merge.field')}
                </th>
                <th scope="col" className="px-3 py-2.5">
                  <ProfileHeading profile={primary} tone="keep" label={t('merge.primary')} />
                </th>
                <th scope="col" className="w-10 px-0 py-2.5 text-center">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t('merge.swap')}
                    onClick={() => setKeepCurrent((value) => !value)}
                    disabled={merge.isPending}
                  >
                    <ArrowLeftRight aria-hidden />
                  </Button>
                </th>
                <th scope="col" className="px-3 py-2.5">
                  <ProfileHeading profile={duplicate} tone="merge" label={t('merge.duplicate')} />
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const kept = row.value(primary)
                const other = row.value(duplicate)
                const filled = Boolean(row.fills && !kept && other)
                return (
                  <tr key={row.label} className="border-t border-border">
                    <th scope="row" className="px-3 py-2 font-semibold text-muted">
                      {row.label}
                    </th>
                    <td className={cn('px-3 py-2', filled && 'bg-accent-soft/50')}>
                      {filled ? (
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="font-semibold text-accent-ink">{other}</span>
                          <Badge tone="accent">{t('merge.willFill')}</Badge>
                        </span>
                      ) : (
                        <span className={cn('text-fg', !kept && 'text-subtle')}>{kept || '—'}</span>
                      )}
                    </td>
                    <td aria-hidden />
                    <td className="px-3 py-2 text-muted">{other || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <p className="text-xs text-muted">{t('merge.keepNote')}</p>

        {failure && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {failure}
          </p>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={merge.isPending}>
            {t('actions.cancel', { ns: 'common' })}
          </Button>
          <Button variant="primary" onClick={confirm} loading={merge.isPending}>
            <Merge aria-hidden />
            {t('merge.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ProfileHeading({ profile, tone, label }: { profile: Profile; tone: 'keep' | 'merge'; label: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <GuestAvatar name={profile.full_name} vip={profile.is_vip} size="sm" />
      <span className="min-w-0">
        <span className={cn('eyebrow block !text-[10px]', tone === 'keep' && '!text-accent-ink')}>{label}</span>
        <span className="block truncate font-semibold text-fg">{profile.full_name}</span>
      </span>
    </span>
  )
}
