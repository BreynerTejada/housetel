import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

/** localStorage key of the persisted session store (only the active property is persisted). */
export const SESSION_STORAGE_KEY = 'housetel.session'

interface SessionState {
  /** Active property of the staff app; sent as `X-Property-Id` by `lib/api`. */
  propertyId: string | null
  setPropertyId: (id: string | null) => void
  /** In memory only: the user logged out on purpose, so guards send them to a plain `/login`. */
  loggedOut: boolean
  setLoggedOut: (loggedOut: boolean) => void
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      propertyId: null,
      setPropertyId: (propertyId) => set({ propertyId }),
      loggedOut: false,
      setLoggedOut: (loggedOut) => set({ loggedOut }),
    }),
    {
      name: SESSION_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: ({ propertyId }) => ({ propertyId }),
    },
  ),
)
