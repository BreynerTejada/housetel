/**
 * The IVA exemption on lodging (Estatuto Tributario art. 481 lit. d): a guest with a foreign nationality who
 * does not live in Colombia. Same rule as the backend (`Guest.is_foreign_non_resident`): a foreigner without a
 * declared residence counts as a non-resident; without a nationality nobody is exempt.
 */
export function isForeignNonResident(nationality: string | null | undefined, residence: string | null | undefined): boolean {
  const country = (nationality ?? '').trim().toUpperCase()
  const home = (residence ?? '').trim().toUpperCase()
  return country !== '' && country !== 'CO' && home !== 'CO'
}
