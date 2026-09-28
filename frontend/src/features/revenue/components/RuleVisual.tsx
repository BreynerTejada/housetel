import { useTranslation } from 'react-i18next'
import { formatDateRange, formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { DayOfWeekParams, EventParams, HolidayParams, LeadTimeParams, OccupancyParams, PricingRule } from '../api'
import { signedPercent } from '../lib/format'
import { WEEKDAYS } from '../lib/rules'
import { STEP_CLASS, stepOf } from '../lib/scale'

/** A 0–100 % bar with each occupancy tier colored by the direction and size of its adjustment. */
export function TierBar({ tiers, className }: { tiers: OccupancyParams['tiers']; className?: string }) {
  const { t } = useTranslation('revenue')
  return (
    <div className={cn('grid gap-1', className)}>
      <div aria-hidden className="relative h-3 overflow-hidden rounded-full bg-stone-soft">
        {tiers.map((tier, index) => (
          <span
            key={index}
            className={cn('absolute inset-y-0 border-x border-surface', STEP_CLASS[stepOf(tier.adjust)])}
            style={{ left: `${Math.max(0, Math.min(100, tier.min))}%`, width: `${Math.max(0, Math.min(100, tier.max) - Math.max(0, tier.min))}%` }}
          />
        ))}
      </div>
      <div aria-hidden className="flex justify-between text-2xs text-subtle">
        <span>0 %</span>
        <span>{t('rules.occupancyAxis')}</span>
        <span>100 %</span>
      </div>
    </div>
  )
}

/** What a rule does, drawn for its kind (read-only summary of the rule card). */
export function RuleVisual({ rule }: { rule: PricingRule }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const adjust = (value: number) => signedPercent(value, lang)

  switch (rule.kind) {
    case 'occupancy': {
      const { tiers } = rule.params as OccupancyParams
      return (
        <div className="grid gap-2">
          <TierBar tiers={tiers} />
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-fg">
            {tiers.map((tier, index) => (
              <li key={index} className="num">
                {t('rules.tier', { from: formatNumber(tier.min, lang), to: formatNumber(tier.max, lang), adjust: adjust(tier.adjust) })}
              </li>
            ))}
          </ul>
        </div>
      )
    }
    case 'lead_time': {
      const { last_minute: lastMinute, early_bird: earlyBird } = rule.params as LeadTimeParams
      return (
        <ul className="grid gap-1 text-xs text-fg">
          {lastMinute.map((window) => (
            <li key={`lm-${window.max_days}`} className="num">
              {window.max_days === 0
                ? t('rules.lastMinuteZero', { adjust: adjust(window.adjust) })
                : t('rules.lastMinute', { count: window.max_days, adjust: adjust(window.adjust) })}
            </li>
          ))}
          {earlyBird.map((window) => (
            <li key={`eb-${window.min_days}`} className="num">
              {t('rules.earlyBird', { count: window.min_days, adjust: adjust(window.adjust) })}
            </li>
          ))}
        </ul>
      )
    }
    case 'day_of_week': {
      const days = rule.params as DayOfWeekParams
      return (
        <ul className="flex gap-1">
          {WEEKDAYS.map((day) => {
            const value = days[day]
            const set = value !== undefined && value !== 0
            return (
              <li
                key={day}
                aria-label={`${t(`weekdays.${day}`)}: ${set ? adjust(value) : t('rules.noTier')}`}
                className={cn(
                  'grid min-w-10 justify-items-center rounded-md px-1 py-1 text-2xs font-bold',
                  set ? STEP_CLASS[stepOf(value)] : 'bg-surface-2 text-subtle',
                )}
              >
                <span aria-hidden>{t(`weekdaysShort.${day}`)}</span>
                <span aria-hidden className="num">{set ? signedPercent(value, lang, { unit: false }) : '·'}</span>
              </li>
            )
          })}
        </ul>
      )
    }
    case 'holiday': {
      const params = rule.params as HolidayParams
      return (
        <p className="num text-xs text-fg">
          {t('rules.holidayValue', { adjust: adjust(params.adjust) })} ·{' '}
          <span className="text-muted">{t(params.include_bridges ? 'rules.withBridges' : 'rules.withoutBridges')}</span>
        </p>
      )
    }
    case 'event': {
      const params = rule.params as EventParams
      return (
        <p className="num text-xs text-fg">
          {params.name && <span className="font-semibold">{params.name} · </span>}
          {t('rules.eventValue', { adjust: adjust(params.adjust), range: formatDateRange(params.start, params.end, lang) })}
        </p>
      )
    }
    default:
      return null
  }
}
