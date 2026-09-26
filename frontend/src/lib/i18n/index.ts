import type { QueryClient } from '@tanstack/react-query'
import i18n, { type Resource } from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import { api } from '../api'
import { queryClient } from '../query'
import commonEn from './locales/en/common.json'
import commonEs from './locales/es/common.json'

export const LANGUAGES = ['es', 'en'] as const
export type Language = (typeof LANGUAGES)[number]
/** Also read by the inline script in index.html to set `<html lang>` before the first paint. */
export const LANGUAGE_STORAGE_KEY = 'housetel.lang'

type Messages = Record<string, unknown>

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value)
}

/**
 * Builds i18next resources: `common` from src/lib/i18n/locales and one namespace per feature,
 * named after its folder (`features/<feature>/locales/<lang>.json`).
 */
export function buildResources(featureFiles: Record<string, Messages>, common: Record<Language, Messages>): Resource {
  const resources: Resource = {}
  for (const lang of LANGUAGES) resources[lang] = { common: common[lang] }
  for (const [path, messages] of Object.entries(featureFiles)) {
    const match = /features\/([^/]+)\/locales\/([^/]+)\.json$/.exec(path)
    if (!match) continue
    const [, feature, lang] = match
    if (!isLanguage(lang)) continue
    resources[lang][feature] = messages
  }
  return resources
}

const featureFiles = import.meta.glob<Messages>('../../features/*/locales/*.json', { eager: true, import: 'default' })
const resources = buildResources(featureFiles, { es: commonEs, en: commonEn })

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    ns: Object.keys(resources.es),
    defaultNS: 'common',
    fallbackNS: 'common',
    fallbackLng: 'es',
    supportedLngs: [...LANGUAGES],
    initAsync: false,
    returnNull: false,
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage'],
      convertDetectedLanguage: (lng: string) => lng.split('-')[0] ?? lng,
    },
  })

function syncDocumentLanguage(lng: string) {
  document.documentElement.setAttribute('lang', isLanguage(lng) ? lng : 'es')
}

syncDocumentLanguage(i18n.resolvedLanguage ?? i18n.language)
i18n.on('languageChanged', syncDocumentLanguage)

/** Current UI language, always one of the supported ones. */
export function currentLanguage(): Language {
  const lng = i18n.resolvedLanguage ?? i18n.language
  return isLanguage(lng) ? lng : 'es'
}

/**
 * Switches the UI language and, when someone is signed in, saves it on their profile
 * (`PATCH /accounts/me/`). The UI keeps the new language even if saving fails.
 */
export async function setLanguage(lang: Language, client: QueryClient = queryClient): Promise<void> {
  await i18n.changeLanguage(lang)
  const me = client.getQueryData<{ language?: string } | null>(['me'])
  if (!me || me.language === lang) return
  try {
    const updated = await api.patch<Record<string, unknown>>('/accounts/me/', { language: lang })
    client.setQueryData(['me'], updated)
  } catch {
    /* not critical: the choice is still stored locally */
  }
}

export default i18n
