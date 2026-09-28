import { toast, type ExternalToast } from 'sonner'

/**
 * Toasts of the calendar. The app's toaster sits bottom-right, right where the booking panel keeps its
 * actions ("Move…", "Open booking"), so calendar toasts go bottom-center — top-center on phones, where the
 * panel is a bottom sheet — and never hide the button someone is about to press.
 */
function position(): ExternalToast['position'] {
  const phone = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 639px)').matches
  return phone ? 'top-center' : 'bottom-center'
}

export const calendarToast = {
  success: (message: string, options?: ExternalToast) => toast.success(message, { position: position(), ...options }),
  error: (message: string, options?: ExternalToast) => toast.error(message, { position: position(), ...options }),
  warning: (message: string, options?: ExternalToast) => toast.warning(message, { position: position(), ...options }),
}
