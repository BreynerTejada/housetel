/**
 * Legal documents of Housetel (plan P6): terms, the personal data policy (Ley 1581 de 2012) and the data
 * processing agreement between each hotel and Housetel. The texts live in `es.ts` / `en.ts` (loaded with the
 * legal page only, never in the global i18n bundle). Placeholders in braces are filled at render time:
 * `{email}` (support e-mail), `{whatsapp}` (support WhatsApp) and `{privacy}`, `{terms}`, `{dpa}` (links).
 */

export type LegalDocId = 'terminos' | 'privacidad' | 'encargo-datos'

export const LEGAL_DOC_IDS: readonly LegalDocId[] = ['terminos', 'privacidad', 'encargo-datos']

/** Public path of each document (the ids are the Spanish slugs the consents link to). */
export const LEGAL_PATHS: Record<LegalDocId, string> = {
  terminos: '/legal/terminos',
  privacidad: '/legal/privacidad',
  'encargo-datos': '/legal/encargo-datos',
}

/** A paragraph, a bulleted list, or a highlighted note. */
export type LegalBlock = string | { list: string[] } | { note: string }

export interface LegalSection {
  /** Anchor (`#id`), stable across languages. */
  id: string
  title: string
  body: LegalBlock[]
}

export interface LegalDocument {
  title: string
  /** One sentence under the title. */
  lead: string
  /** "In short": three or four plain-language bullets before the full text. */
  summary: string[]
  sections: LegalSection[]
}

export type LegalTexts = Record<LegalDocId, LegalDocument>

/** Version shown on every document (bump it with each substantive change). */
export const LEGAL_VERSION = '1.0'
export const LEGAL_EFFECTIVE_DATE = '2026-09-28'
