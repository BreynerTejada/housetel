/** NIT (Colombian tax id) helpers: the DIAN check digit (DV, modulo 11) and the usual display "900.123.456-7". */

const WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
export const MAX_NIT_DIGITS = WEIGHTS.length

/** `"900.123.456-7"` → `{ digits: "900123456", dv: "7" }`. */
export function splitNit(value: string): { digits: string; dv: string } {
  const [base = '', dv = ''] = value.split('-')
  return { digits: base.replace(/\D/g, ''), dv: dv.replace(/\D/g, '').slice(0, 1) }
}

/** DV of a NIT without its check digit. */
export function checkDigit(nit: string): string {
  const digits = nit.replace(/\D/g, '')
  const total = [...digits].reverse().reduce((sum, digit, index) => sum + Number(digit) * (WEIGHTS[index] ?? 0), 0)
  const remainder = total % 11
  return String(remainder > 1 ? 11 - remainder : remainder)
}

/** `"900123456", "7"` → `"900.123.456-7"`. */
export function formatNit(nit: string, dv = ''): string {
  const digits = nit.replace(/\D/g, '')
  if (!digits) return ''
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return dv ? `${grouped}-${dv}` : grouped
}
