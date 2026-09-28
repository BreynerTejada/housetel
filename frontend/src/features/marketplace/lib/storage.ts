/**
 * The confirmation page opens a booking with its code and the booker's email. After the payment gateway sends
 * the guest back, the email comes from here: per tab (sessionStorage), never across browser sessions, and every
 * access tolerates a blocked storage.
 */
const key = (code: string) => `housetel.booking.${code.toUpperCase()}`

export function rememberBookingEmail(code: string, email: string): void {
  try {
    sessionStorage.setItem(key(code), email)
  } catch {
    /* private mode or blocked storage: the page will ask for the email */
  }
}

export function recallBookingEmail(code: string): string | null {
  try {
    return sessionStorage.getItem(key(code))
  } catch {
    return null
  }
}
