import { useEffect } from 'react'
import { isLanguage, setLanguage } from '@/lib/i18n'

const APPLIED_PREFIX = 'housetel.portal.lang:'

/**
 * The first time a guest opens the link of a booking, the portal speaks the language the booking was made
 * in. After that the guest's own choice (language toggle, stored by i18n) wins.
 */
export function useReservationLanguage(code: string | undefined, language: string | undefined): void {
  useEffect(() => {
    if (!code || !isLanguage(language)) return
    const key = APPLIED_PREFIX + code
    try {
      if (localStorage.getItem(key)) return
      localStorage.setItem(key, '1')
    } catch {
      return // storage unavailable: keep whatever language the browser chose
    }
    void setLanguage(language)
  }, [code, language])
}
