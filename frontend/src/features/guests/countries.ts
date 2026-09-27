/** ISO 3166-1 alpha-2 countries; names come from the browser (`Intl.DisplayNames`) in the UI language. */

// Most frequent origins of guests in Colombian hotels first, then every other country.
export const FREQUENT_COUNTRIES = ['CO', 'US', 'ES', 'MX', 'AR', 'BR', 'VE', 'EC', 'PE', 'CL', 'PA', 'CA', 'FR', 'DE', 'GB', 'IT']

const ALL_CODES = (
  'AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ ' +
  'CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO ' +
  'FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE ' +
  'JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO ' +
  'MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW ' +
  'PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM ' +
  'TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'
).split(' ')

const displayNames = new Map<string, Intl.DisplayNames | null>()

function namesFor(lang: string): Intl.DisplayNames | null {
  if (!displayNames.has(lang)) {
    try {
      displayNames.set(lang, new Intl.DisplayNames([lang], { type: 'region' }))
    } catch {
      displayNames.set(lang, null)
    }
  }
  return displayNames.get(lang) ?? null
}

/** "CO" → "Colombia" (in `lang`); unknown or empty codes come back as they are. */
export function countryName(code: string | null | undefined, lang = 'es'): string {
  if (!code) return ''
  const upper = code.toUpperCase()
  try {
    return namesFor(lang)?.of(upper) ?? upper
  } catch {
    return upper
  }
}

export interface CountryOption {
  value: string
  label: string
  description?: string
  keywords?: string[]
}

/** Options for a country combobox: frequent origins first, then the rest alphabetically. */
export function countryOptions(lang = 'es'): CountryOption[] {
  const rest = ALL_CODES.filter((code) => !FREQUENT_COUNTRIES.includes(code))
    .map((code) => ({ code, name: countryName(code, lang) }))
    .sort((a, b) => a.name.localeCompare(b.name, lang))
  return [...FREQUENT_COUNTRIES.map((code) => ({ code, name: countryName(code, lang) })), ...rest].map(({ code, name }) => ({
    value: code,
    label: name,
    description: code,
    keywords: [code],
  }))
}
