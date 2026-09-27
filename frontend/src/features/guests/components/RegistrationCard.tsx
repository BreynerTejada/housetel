import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { formatDate, normalizeLang } from '@/lib/format'
import type { Guest } from '../api'
import { countryName } from '../countries'
import { formatDocument } from '../format'
import { GuestAvatar } from './GuestAvatar'

const HOLES = 6

/**
 * The guest profile header, drawn like the hotel registration card (TRA): a perforated tear-off edge and
 * the identity data in ruled boxes, the way the paper form is filled in at the front desk.
 */
export function RegistrationCard({ guest, actions }: { guest: Guest; actions?: ReactNode }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const anonymized = Boolean(guest.anonymized_at)
  const residence = [guest.city_of_residence, countryName(guest.country_of_residence, lang)].filter(Boolean).join(', ')
  const fields: { label: string; value: string; mono?: boolean }[] = [
    { label: t('detail.card.document'), value: formatDocument(guest.document_type, guest.document_number), mono: true },
    { label: t('detail.card.nationality'), value: countryName(guest.nationality, lang) },
    { label: t('detail.card.residence'), value: residence },
    { label: t('detail.card.language'), value: guest.language ? t(`languages.${guest.language}`, { ns: 'common' }) : '' },
    { label: t('detail.card.birthDate'), value: guest.birth_date ? formatDate(guest.birth_date, undefined, lang) : '', mono: true },
    { label: t('detail.card.since'), value: formatDate(guest.created_at, 'MMM yyyy', lang), mono: true },
  ]

  return (
    <section
      aria-label={t('detail.card.label')}
      className="relative overflow-hidden rounded-xl border border-border bg-surface shadow-xs"
    >
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 flex w-6 flex-col items-center justify-evenly border-r border-dashed border-border-strong/70 bg-surface-2/70"
      >
        {Array.from({ length: HOLES }, (_, index) => (
          <span key={index} className="size-2 rounded-full bg-bg shadow-[inset_0_1px_2px_rgb(0_0_0/0.22)]" />
        ))}
      </div>

      <div className="py-5 pr-4 pl-10 sm:pr-6 sm:pl-12">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <GuestAvatar name={guest.full_name} vip={guest.is_vip} muted={anonymized} size="lg" />
            <div className="min-w-0">
              <p className="eyebrow">{t('detail.card.label')}</p>
              <h1 className="mt-0.5 text-[26px] leading-8 font-extrabold tracking-[-0.03em] break-words text-fg">
                {guest.full_name}
              </h1>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {guest.is_vip && <Badge tone="accent">{t('badges.vip')}</Badge>}
                {guest.is_foreign_non_resident && (
                  <Tooltip content={t('badges.taxExemptHint')}>
                    <Badge tone="info" tabIndex={0}>
                      {t('badges.taxExempt')}
                    </Badge>
                  </Tooltip>
                )}
                {guest.blacklisted && <Badge tone="danger">{t('badges.blacklisted')}</Badge>}
                {anonymized && <Badge tone="stone">{t('badges.anonymized')}</Badge>}
                {guest.merged_into && <Badge tone="stone">{t('badges.merged')}</Badge>}
                {guest.tags.map((tag) => (
                  <Badge key={tag}>{tag}</Badge>
                ))}
              </div>
            </div>
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>

        <dl className="mt-5 grid grid-cols-2 overflow-hidden rounded-lg border border-border sm:grid-cols-3 lg:grid-cols-6">
          {fields.map((field) => (
            <div key={field.label} className="-mr-px -mb-px border-r border-b border-border px-3 py-2.5">
              <dt className="eyebrow !text-[10px]">{field.label}</dt>
              {/* Identity data wraps instead of being cut: the front desk reads document numbers off this card. */}
              <dd className={field.mono ? 'num mt-0.5 font-semibold break-words text-fg' : 'mt-0.5 font-semibold break-words text-fg'}>
                {field.value || <span className="font-normal text-subtle">—</span>}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}
