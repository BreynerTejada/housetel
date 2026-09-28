/** Radius of the data end of a bar (dataviz: 4px rounded data-end, square at the baseline). */
const RADIUS = 4

/**
 * SVG path of a bar whose data end is rounded: `top` for a value above the baseline, `bottom` for a value
 * below it, `none` for a segment in the middle of a stack. Accepts a negative height (Recharts draws bars
 * below the baseline that way) and normalizes it.
 */
export function barPath(x: number, y: number, width: number, height: number, end: 'top' | 'bottom' | 'none'): string {
  const top = Math.min(y, y + height)
  const h = Math.abs(height)
  const w = Math.max(width, 0)
  if (!w || !h) return ''
  const r = Math.min(RADIUS, w / 2, h)
  const right = x + w
  const bottom = top + h
  if (end === 'top') {
    return `M${x},${bottom}V${top + r}Q${x},${top} ${x + r},${top}H${right - r}Q${right},${top} ${right},${top + r}V${bottom}Z`
  }
  if (end === 'bottom') {
    return `M${x},${top}H${right}V${bottom - r}Q${right},${bottom} ${right - r},${bottom}H${x + r}Q${x},${bottom} ${x},${bottom - r}Z`
  }
  return `M${x},${top}H${right}V${bottom}H${x}Z`
}
