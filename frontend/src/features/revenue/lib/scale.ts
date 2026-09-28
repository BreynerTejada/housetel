/**
 * Diverging scale of the revenue heatmap: how much the recommended price moves a night (% vs the current
 * price). Cool slate = lower the price, warm terracotta = raise it, the neutral stone of the design system =
 * no change. Three equal steps per arm: under 6 %, 6–12 %, 12 % or more (a boundary belongs to the stronger
 * step). Cells always print their signed % too, so the color never carries the value alone.
 *
 * The steps are OKLab mixes of the system's `--info` (slate) and `--accent` (terracotta) with the card surface,
 * solved so both arms have the same lightness per step (light 0.87 / 0.76 / 0.645, dark 0.365 / 0.485 / 0.635).
 * Checked with the dataviz validator (`--ordinal` per arm): one hue, monotone lightness, every gap ≥ 0.06
 * (neutral → first step included). The palest step recedes toward the surface on purpose (heatmap "near
 * zero"); the printed value and the list view are the relief channel. Text: ink on every light-theme step
 * (≥ 4.96:1); light ink on the dark theme's first two steps (≥ 5.31:1) and dark ink on the strongest
 * (≥ 5.08:1).
 */

export type Step = -3 | -2 | -1 | 0 | 1 | 2 | 3

export const STEP_LIMITS = [6, 12] as const

export const LEGEND_STEPS: Step[] = [-3, -2, -1, 0, 1, 2, 3]

/** Step of a change in percentage points (API strings like "12.00" or numbers). */
export function stepOf(changePercent: string | number): Step {
  const change = Number(changePercent)
  if (!Number.isFinite(change) || change === 0) return 0
  const size = Math.abs(change)
  const magnitude = size >= STEP_LIMITS[1] ? 3 : size >= STEP_LIMITS[0] ? 2 : 1
  return (change > 0 ? magnitude : -magnitude) as Step
}

/** Fill + text of each step, light and dark theme (full class strings so Tailwind generates them). */
export const STEP_CLASS: Record<Step, string> = {
  [-3]: 'bg-[#7a91a6] text-fg dark:bg-[#718eab] dark:text-on-accent',
  [-2]: 'bg-[#a3b3c3] text-fg dark:bg-[#516171]',
  [-1]: 'bg-[#cdd5de] text-fg dark:bg-[#383f47]',
  0: 'bg-stone-soft text-muted',
  1: 'bg-[#eccdc3] text-fg dark:bg-[#52372d]',
  2: 'bg-[#d9a291] text-fg dark:bg-[#845040]',
  3: 'bg-[#c4775e] text-fg dark:bg-[#c67057] dark:text-on-accent',
}

/** Outline of a decided (applied) recommendation: the arm's middle step, so its direction still reads. */
export const STEP_RING: Record<Step, string> = {
  [-3]: 'shadow-[inset_0_0_0_2px_#a3b3c3] dark:shadow-[inset_0_0_0_2px_#516171]',
  [-2]: 'shadow-[inset_0_0_0_2px_#a3b3c3] dark:shadow-[inset_0_0_0_2px_#516171]',
  [-1]: 'shadow-[inset_0_0_0_2px_#a3b3c3] dark:shadow-[inset_0_0_0_2px_#516171]',
  0: 'shadow-[inset_0_0_0_2px_var(--border-strong)]',
  1: 'shadow-[inset_0_0_0_2px_#d9a291] dark:shadow-[inset_0_0_0_2px_#845040]',
  2: 'shadow-[inset_0_0_0_2px_#d9a291] dark:shadow-[inset_0_0_0_2px_#845040]',
  3: 'shadow-[inset_0_0_0_2px_#d9a291] dark:shadow-[inset_0_0_0_2px_#845040]',
}
