import { ArrowUpRight, CircleDollarSign, Star } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { StayStatus } from '../api'
import { STATUS_COLORS, STATUSES } from '../lib/constants'

/** What the colors and marks of the grid mean, plus how to use it with the pointer. */
export function CalendarLegend({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation('calendar')
  return (
    <section aria-label={t('legend.title')} className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
      <ul className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
        {STATUSES.map((status: StayStatus) => (
          <li key={status} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-3 w-5 rounded-[4px]"
              style={{
                background: STATUS_COLORS[status].fill,
                boxShadow: `inset 3px 0 0 ${STATUS_COLORS[status].edge}`,
                border: status === 'tentative' ? `1px dashed ${STATUS_COLORS[status].edge}` : undefined,
              }}
            />
            {t(`status.reservation.${status}`, { ns: 'common' })}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="hatch h-3 w-5 rounded-[4px] border border-stone/30 bg-stone-soft" />
          {t('legend.blocked')}
        </li>
        <li className="flex items-center gap-1">
          <Star aria-hidden className="size-3 fill-current text-accent-ink" />
          {t('legend.vip')}
        </li>
        <li className="flex items-center gap-1">
          <CircleDollarSign aria-hidden className="size-3 text-warning-ink" />
          {t('legend.balanceDue')}
        </li>
        <li className="flex items-center gap-1">
          <ArrowUpRight aria-hidden className="size-3 text-fg" />
          {t('legend.upgrade')}
        </li>
      </ul>
      {canManage && <p className="basis-full text-subtle lg:basis-auto">{t('legend.hint')}</p>}
    </section>
  )
}
