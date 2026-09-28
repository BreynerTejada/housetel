import type { StayStatus } from '../api'

/** Days on screen the toolbar offers. */
export const SPANS = [7, 14, 30] as const

/** Statuses `GET calendar/` returns (cancelled and no-show stays never come back), in lifecycle order. */
export const STATUSES: readonly StayStatus[] = ['tentative', 'confirmed', 'checked_in', 'checked_out']

/**
 * Calendar dialogs that can grow taller than the screen (the key rack of a big hotel or a hostel, the quick
 * booking on a phone): header and footer stay put around a body that scrolls, so the main button is always in
 * reach. Classes laid over the shared dialog, which otherwise scrolls as a whole.
 */
export const SCROLL_DIALOG = {
  content: 'flex flex-col gap-0 overflow-hidden p-0',
  header: 'pt-6 pr-12 pb-4 pl-6',
  body: 'grid min-h-0 flex-1 content-start gap-4 overflow-y-auto px-6 pt-1 pb-5',
  footer: 'mt-0 flex-row items-center justify-end border-t border-border px-6 py-3',
} as const

/** Colors of a reservation state (design tokens `--status-*`): soft fill, readable ink, solid edge. */
export const STATUS_COLORS: Record<StayStatus, { fill: string; ink: string; edge: string }> = {
  tentative: { fill: 'var(--status-tentative-soft)', ink: 'var(--status-tentative-ink)', edge: 'var(--status-tentative)' },
  confirmed: { fill: 'var(--status-confirmed-soft)', ink: 'var(--status-confirmed-ink)', edge: 'var(--status-confirmed)' },
  checked_in: { fill: 'var(--status-checked-in-soft)', ink: 'var(--status-checked-in-ink)', edge: 'var(--status-checked-in)' },
  checked_out: { fill: 'var(--status-checked-out-soft)', ink: 'var(--status-checked-out-ink)', edge: 'var(--status-checked-out)' },
}
