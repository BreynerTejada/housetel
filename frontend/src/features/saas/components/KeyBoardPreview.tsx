import { useTranslation } from 'react-i18next'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { PublicPlan } from '../api'
import { pickText } from '../helpers'

const MAX_HOOKS = 40

/**
 * The signup's signature: the key board of the hotel being created, drawn live from the form — its brass
 * plate carries the name and city, one hook per room or bed (a bed hostel is a board full of keys), and the
 * plan tag that fits hangs at the end. Same key-tag language as the login rack.
 */
export function KeyBoardPreview({
  hotelName,
  city,
  typeLabel,
  units,
  plan,
  compact = false,
}: {
  hotelName: string
  city: string
  typeLabel: string
  units: number
  plan: PublicPlan | null
  compact?: boolean
}) {
  const { t, i18n } = useTranslation('saas')
  const limit = compact ? 20 : MAX_HOOKS
  const shown = Math.max(0, Math.min(units, limit))
  const extra = units - shown
  const hooks = Array.from({ length: Math.max(shown, compact ? 10 : 20) }, (_, index) => index < shown)
  const name = hotelName.trim() || t('signup.preview.placeholderName')

  return (
    <figure
      aria-label={t('signup.preview.label', { name, count: units })}
      className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5"
    >
      {/* Brass plate */}
      <div className="flex items-start justify-between gap-3 rounded-lg border border-accent/25 bg-accent-soft px-4 py-3">
        <div className="min-w-0">
          <p className="eyebrow !text-accent-ink/80">{typeLabel || t('signup.preview.type')}</p>
          <p className="truncate text-[20px] leading-tight font-extrabold tracking-[-0.03em] text-accent-ink">{name}</p>
          <p className="truncate text-sm text-accent-ink/80">{city.trim() || t('signup.preview.city')}</p>
        </div>
        <p className="num shrink-0 text-right text-xs font-semibold text-accent-ink/80">
          <span className="block text-[22px] leading-none font-extrabold text-accent-ink">{units || 0}</span>
          {t('signup.preview.units', { count: units || 0 })}
        </p>
      </div>

      {/* Hooks */}
      <ul aria-hidden className="grid grid-cols-10 gap-1.5">
        {hooks.map((filled, index) => (
          <li
            key={index}
            className={cn(
              'relative h-8 rounded-md transition-colors duration-500 motion-reduce:transition-none',
              filled ? 'bg-room-clean-soft' : 'border border-dashed border-border bg-transparent',
            )}
          >
            <span
              className={cn(
                'absolute top-1.5 left-1/2 size-1.5 -translate-x-1/2 rounded-full',
                filled ? 'bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]' : 'bg-border',
              )}
            />
            {filled && (
              <span className="num absolute right-1 bottom-0.5 text-[9px] font-bold text-success-ink">{index + 1}</span>
            )}
          </li>
        ))}
      </ul>
      {extra > 0 && <p className="num -mt-2 text-xs text-muted">{t('signup.preview.more', { count: extra })}</p>}

      {/* Plan tag */}
      {plan && (
        <figcaption className="flex flex-wrap items-center justify-between gap-2 border-t border-dashed border-border pt-3">
          <span className="text-sm text-muted">{t('signup.preview.plan')}</span>
          <span className="inline-flex items-center gap-2 rounded-full border border-border-strong bg-surface-2 px-3 py-1 text-sm font-semibold text-fg">
            {pickText(plan.name, i18n.language)}
            <span className="num font-medium text-muted">
              {t('signup.preview.price', { price: formatMoney(plan.price_monthly) })}
            </span>
          </span>
        </figcaption>
      )}
    </figure>
  )
}
