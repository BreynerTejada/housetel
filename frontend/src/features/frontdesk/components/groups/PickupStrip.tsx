import { useTranslation } from 'react-i18next'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BlockNight } from '../../api'

/** Up to this many units a night is drawn as one slot per unit; above it, as a proportional column. */
const MAX_SLOTS = 8
const SLOT = 7
const GAP = 3
const COLUMN_HEIGHT = MAX_SLOTS * (SLOT + GAP) - GAP

/**
 * The allotment night by night, drawn like the key rack of the front desk (pilot P3): each night is a column of
 * key slots — taken by the group (filled in the category's color), still held for it (dashed terracotta) or,
 * once the block is released, given back to general sale (hatched). The thin nights stand out at a glance.
 */
export function PickupStrip({
  nights,
  color,
  released,
  bd,
  label,
}: {
  nights: BlockNight[]
  /** The category's color (as on the calendar). */
  color: string
  released: boolean
  /** Business date: tonight's column is marked. */
  bd: string
  /** Accessible name of the whole strip. */
  label: string
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const units = nights[0]?.units ?? 0
  const slots = units <= MAX_SLOTS
  // One slot per unit sizes the column to the block; a big block is a proportional column of fixed height.
  const height = slots ? Math.max(1, units) * (SLOT + GAP) - GAP : COLUMN_HEIGHT

  return (
    <div className="grid gap-2">
      <ol aria-label={label} className="flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:thin]">
        {nights.map((night) => {
          const picked = Math.min(night.picked, night.units)
          const held = released ? 0 : Math.min(night.remaining, night.units - picked)
          const freed = Math.max(0, night.units - picked - held)
          const tonight = night.date === bd
          return (
            <li
              key={night.date}
              aria-label={t('groups.blocks.night', {
                date: formatDate(night.date, lang === 'en' ? 'EEE MMM d' : 'EEE d MMM', lang),
                picked: night.picked,
                held,
                units: night.units,
              })}
              className="flex min-w-10 flex-col items-center justify-end gap-1.5"
            >
              <span aria-hidden className="flex w-8 flex-col-reverse justify-start" style={{ height, gap: GAP }}>
                {slots ? (
                  <>
                    {Array.from({ length: picked }, (_, index) => (
                      <span key={`p${index}`} className="w-full shrink-0 rounded-[2px]" style={{ height: SLOT, backgroundColor: color }} />
                    ))}
                    {Array.from({ length: held }, (_, index) => (
                      <span
                        key={`h${index}`}
                        className="w-full shrink-0 rounded-[2px] border border-dashed border-accent/70 bg-accent-soft/50"
                        style={{ height: SLOT }}
                      />
                    ))}
                    {Array.from({ length: freed }, (_, index) => (
                      <span key={`f${index}`} className="hatch w-full shrink-0 rounded-[2px] bg-stone-soft" style={{ height: SLOT }} />
                    ))}
                  </>
                ) : (
                  <span className="flex h-full w-full flex-col-reverse overflow-hidden rounded-[3px] bg-surface-3">
                    <span style={{ height: `${(picked / night.units) * 100}%`, backgroundColor: color }} />
                    <span className="border-y border-dashed border-accent/70 bg-accent-soft/60" style={{ height: `${(held / night.units) * 100}%` }} />
                    <span className="hatch bg-stone-soft" style={{ height: `${(freed / night.units) * 100}%` }} />
                  </span>
                )}
              </span>
              <span
                aria-hidden
                className={cn(
                  'num text-center text-[10px] leading-3 text-muted',
                  tonight && 'rounded-sm bg-accent-soft px-1 font-bold text-accent-ink',
                )}
              >
                <span className="block capitalize">{formatDate(night.date, 'EEEEEE', lang)}</span>
                <span className="block font-semibold text-fg">{formatDate(night.date, 'd', lang)}</span>
              </span>
            </li>
          )
        })}
      </ol>
      <p aria-hidden className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        <span className="inline-flex items-center gap-1">
          <span className="h-[7px] w-3 rounded-[2px]" style={{ backgroundColor: color }} />
          {t('groups.blocks.legendPicked')}
        </span>
        {!released && (
          <span className="inline-flex items-center gap-1">
            <span className="h-[7px] w-3 rounded-[2px] border border-dashed border-accent/70 bg-accent-soft/50" />
            {t('groups.blocks.legendHeld')}
          </span>
        )}
        {released && (
          <span className="inline-flex items-center gap-1">
            <span className="hatch h-[7px] w-3 rounded-[2px] bg-stone-soft" />
            {t('groups.blocks.legendFreed')}
          </span>
        )}
      </p>
    </div>
  )
}
