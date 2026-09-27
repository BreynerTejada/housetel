import type { DocumentType, GuestInput } from './api'

const GROUPED_DOCUMENTS = new Set(['CC', 'CE', 'TI', 'NIT'])

/** "CC 52.123.456" (Colombian IDs read with thousands dots), "PA X1234567"; `''` without number. */
export function formatDocument(type: string | null | undefined, number: string | null | undefined): string {
  if (!number) return ''
  const [base = '', check] = number.split('-')
  const shown =
    type && GROUPED_DOCUMENTS.has(type) && /^\d+$/.test(base)
      ? base.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (check ? `-${check}` : '')
      : number
  return type ? `${type} ${shown}` : shown
}

/** "+57 300 111 2233" for Colombian mobiles and landlines; other numbers stay in E.164. */
export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return ''
  const co = /^\+57(\d{3})(\d{3})(\d{4})$/.exec(phone)
  return co ? `+57 ${co[1]} ${co[2]} ${co[3]}` : phone
}

const EMAIL = /^[^\s@]+@[^\s@]+$/
const DIGITS = /^[\d.\s-]+$/

/**
 * What the user typed in a guest search → a head start for the "new guest" form: an email, a phone
 * (starts with + or has 7+ digits after a 3), a document (digits only) or first/last names.
 */
export function prefillFromQuery(query: string): Partial<GuestInput> {
  const text = query.trim()
  if (!text) return {}
  if (EMAIL.test(text)) return { email: text }
  const digits = text.replace(/\D/g, '')
  if (text.startsWith('+') || (DIGITS.test(text) && digits.length === 10 && digits.startsWith('3'))) {
    return { phone: text }
  }
  if (DIGITS.test(text)) return { document_number: digits }
  const [first = '', ...rest] = text.split(/\s+/)
  return { first_name: first, last_name: rest.join(' ') }
}

export function documentLabelKey(type: DocumentType | '' | string): string {
  return `guests:documentTypes.${type || 'none'}`
}
