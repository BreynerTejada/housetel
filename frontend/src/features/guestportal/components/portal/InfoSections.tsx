import { Clock3, FileText, Globe, Mail, MapPin, Phone } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { formatDate, normalizeLang } from '@/lib/format'
import { invoicePdfUrl, useInvoices, type PortalProperty } from '../../api'
import { tr } from '../../lib/text'

/** Electronic invoices (C7). Hidden while that endpoint answers 404, fails or has nothing yet. */
export function InvoicesSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const invoices = useInvoices(token)
  if (!invoices.data?.length) return null

  return (
    <section aria-labelledby="invoices-title" className="grid gap-3">
      <h2 id="invoices-title" className="text-lg font-bold">
        {t('invoices.title')}
      </h2>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {invoices.data.map((invoice) => (
          <li key={invoice.id} className="flex items-center gap-3 px-4 py-3">
            <FileText aria-hidden className="size-5 shrink-0 text-muted" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">
                {t(`invoices.kinds.${invoice.kind}`, { defaultValue: t('invoices.kinds.invoice') })} {invoice.number}
              </p>
              <p className="text-[13px] text-muted">
                {invoice.issued_at ? formatDate(invoice.issued_at, undefined, lang) : null}
                {invoice.issued_at ? ' · ' : null}
                <MoneyText value={invoice.total} />
              </p>
            </div>
            <a
              href={invoicePdfUrl(token, invoice)}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 text-sm font-semibold text-accent-ink underline-offset-4 hover:underline"
            >
              {t('invoices.download')}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** How to reach the hotel and its house rules. */
export function HotelInfo({ property }: { property: PortalProperty }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const rules = tr(property.house_rules, lang)
  const place = [property.address, property.city].filter(Boolean).join(', ')
  const mapUrl = place ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${property.name}, ${place}`)}` : null

  return (
    <section aria-labelledby="hotel-title" className="grid gap-3">
      <h2 id="hotel-title" className="text-lg font-bold">
        {t('hotel.title')}
      </h2>
      <div className="grid gap-3 rounded-2xl border border-border bg-surface p-5 text-sm">
        {place && (
          <p className="flex items-start gap-2.5">
            <MapPin aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
            <span>
              {place}
              {mapUrl && (
                <a href={mapUrl} target="_blank" rel="noreferrer" className="ml-2 font-semibold text-accent-ink underline-offset-4 hover:underline">
                  {t('hotel.map')}
                </a>
              )}
            </span>
          </p>
        )}
        {(property.check_in_time || property.check_out_time) && (
          <p className="flex items-start gap-2.5">
            <Clock3 aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
            <span>
              {[
                property.check_in_time && t('hotel.checkin', { time: property.check_in_time }),
                property.check_out_time && t('hotel.checkout', { time: property.check_out_time }),
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {property.phone && (
            <a href={`tel:${property.phone.replace(/[^\d+]/g, '')}`} className={chip}>
              <Phone aria-hidden className="size-4" />
              {property.phone}
            </a>
          )}
          {property.email && (
            <a href={`mailto:${property.email}`} className={chip}>
              <Mail aria-hidden className="size-4" />
              {t('hotel.email')}
            </a>
          )}
          {property.website && (
            <a href={property.website} target="_blank" rel="noreferrer" className={chip}>
              <Globe aria-hidden className="size-4" />
              {t('hotel.website')}
            </a>
          )}
        </div>
        {rules && (
          <details className="border-t border-border pt-3">
            <summary className="cursor-pointer font-semibold">{t('hotel.rules')}</summary>
            <p className="mt-2 whitespace-pre-line text-muted">{rules}</p>
          </details>
        )}
      </div>
    </section>
  )
}

const chip =
  'inline-flex min-h-10 items-center gap-2 rounded-full border border-border px-3.5 py-2 font-semibold transition-colors hover:border-border-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55'
