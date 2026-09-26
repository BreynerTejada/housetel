import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import i18n, { buildResources, LANGUAGE_STORAGE_KEY, setLanguage } from '@/lib/i18n'
import { queryClient } from '@/lib/query'
import { server } from '@/test/server'

beforeEach(() => {
  document.cookie = 'csrftoken=t; path=/'
})

afterEach(async () => {
  queryClient.clear()
  await i18n.changeLanguage('es')
})

describe('buildResources', () => {
  it('uses the feature folder as namespace and the file name as language', () => {
    const resources = buildResources(
      {
        '../../features/calendar/locales/es.json': { nav: { calendar: 'Calendario' } },
        '../../features/calendar/locales/en.json': { nav: { calendar: 'Calendar' } },
        '../../features/rates/locales/es.json': { nav: { rates: 'Tarifas' } },
      },
      { es: { hello: 'Hola' }, en: { hello: 'Hello' } },
    )

    expect(resources).toEqual({
      es: { common: { hello: 'Hola' }, calendar: { nav: { calendar: 'Calendario' } }, rates: { nav: { rates: 'Tarifas' } } },
      en: { common: { hello: 'Hello' }, calendar: { nav: { calendar: 'Calendar' } } },
    })
  })

  it('ignores files for unsupported languages', () => {
    const resources = buildResources({ '../../features/calendar/locales/pt.json': { a: 'b' } }, { es: {}, en: {} })
    expect(resources).toEqual({ es: { common: {} }, en: { common: {} } })
  })
})

describe('i18n instance', () => {
  it('falls back to Spanish and exposes the common namespace by default', () => {
    expect(i18n.options.fallbackLng).toEqual(['es'])
    expect(i18n.t('actions.cancel')).toBe('Cancelar')
    expect(i18n.t('actions.cancel', { lng: 'en' })).toBe('Cancel')
  })

  it('has the same keys in Spanish and English for every namespace', () => {
    const flatten = (value: unknown, prefix = ''): string[] =>
      value && typeof value === 'object'
        ? Object.entries(value).flatMap(([key, child]) => flatten(child, `${prefix}${key}.`))
        : [prefix.slice(0, -1)]
    const store = i18n.store.data as Record<string, Record<string, unknown>>
    const namespaces = new Set([...Object.keys(store.es ?? {}), ...Object.keys(store.en ?? {})])

    for (const ns of namespaces) {
      const es = flatten(store.es?.[ns]).sort()
      const en = flatten(store.en?.[ns]).sort()
      expect({ ns, keys: en }).toEqual({ ns, keys: es })
    }
  })
})

describe('setLanguage', () => {
  it('switches the UI, remembers the choice and saves it on the signed-in profile', async () => {
    queryClient.setQueryData(['me'], { id: 'u1', email: 'owner@casaaurora.co', language: 'es' })
    let body: unknown
    server.use(
      http.patch('/api/v1/accounts/me/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'u1', email: 'owner@casaaurora.co', language: 'en' })
      }),
    )

    await setLanguage('en')

    expect(i18n.language).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en')
    expect(body).toEqual({ language: 'en' })
    expect(queryClient.getQueryData<{ language: string }>(['me'])?.language).toBe('en')
  })

  it('does not call the API for anonymous visitors', async () => {
    queryClient.setQueryData(['me'], null)

    // Any request would be unhandled and fail the test.
    await setLanguage('en')

    expect(i18n.language).toBe('en')
  })
})
