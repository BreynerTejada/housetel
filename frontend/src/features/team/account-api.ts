/**
 * Account security data layer (P2): forgot / reset password, change password and email verification
 * (backend `/api/v1/accounts/me/…` and `/api/v1/public/accounts/…`, see docs/integration-notes/P2-accounts.md).
 */
import { useMutation, useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, publicApi } from '@/lib/api'
import { ME_QUERY_KEY, type Me } from '@/lib/auth'
import { useSession } from '@/lib/session'

/** `Me` with both P2 fields (`lib/auth.tsx` may declare only `email_verified`; P-INT adds `email_verified_at`). */
export type AccountMe = Me & { email_verified?: boolean; email_verified_at?: string | null }

/** Only an explicit `false` counts: an older backend without the field never shows the reminder. */
export function isEmailUnverified(me: Me | null | undefined): boolean {
  return (me as AccountMe | null | undefined)?.email_verified === false
}

export function emailVerifiedAt(me: Me | null | undefined): string | null {
  return (me as AccountMe | null | undefined)?.email_verified_at ?? null
}

export interface ResetLinkInfo {
  /** Masked address of the account (`v•••@casaaurora.co`). */
  email: string
}

export interface VerifyEmailResult {
  email: string
  email_verified: boolean
  already_verified: boolean
}

export interface ResendResult {
  sent: boolean
  email: string
  email_verified: boolean
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

export interface ResetPasswordPayload {
  uid: string
  token: string
  new_password: string
}

// ---- Public (no session) --------------------------------------------------------------------------

export function useForgotPassword() {
  return useMutation({
    mutationFn: (email: string) => publicApi.post<{ detail: string }>('/accounts/password/forgot/', { email }),
  })
}

/** Whether a reset link still works (asked before the user types a new password). */
export function useResetLink(uid: string, token: string) {
  return useQuery({
    queryKey: ['password-reset-link', uid, token],
    queryFn: () => publicApi.post<ResetLinkInfo>('/accounts/password/reset/check/', { uid, token }),
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

/**
 * Sets the new password: the backend signs this browser in (and every other session out). Whatever was
 * cached for someone else signed in on this device is dropped before storing the new `Me`.
 */
export function useResetPassword() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ResetPasswordPayload) => publicApi.post<Me>('/accounts/password/reset/', payload),
    onSuccess: async (me) => {
      const staleData = (query: Query) => query.queryKey[0] !== ME_QUERY_KEY[0]
      await queryClient.cancelQueries({ predicate: staleData })
      queryClient.removeQueries({ predicate: staleData })
      useSession.getState().setLoggedOut(false)
      useSession.getState().setPropertyId(null)
      queryClient.setQueryData(ME_QUERY_KEY, me)
    },
  })
}

/** Confirms the address of an emailed link. A query (not a mutation) so a remount never posts twice. */
export function useVerifyEmail(token: string) {
  return useQuery({
    queryKey: ['verify-email', token],
    queryFn: () => publicApi.post<VerifyEmailResult>('/accounts/verify-email/', { token }),
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

// ---- Signed in -----------------------------------------------------------------------------------

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: ChangePasswordPayload) => api.post<{ detail: string }>('/accounts/me/password/', payload),
  })
}

export function useResendVerification() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ResendResult>('/accounts/me/verify-email/resend/'),
    onSuccess: (result) => {
      if (result.sent) markVerificationSent()
      // Verified meanwhile (another tab, the link on the phone): refresh `Me` so the reminders go away.
      if (result.email_verified) void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
    },
  })
}

// ---- Resend cooldown (shared by the topbar chip and the account page) ------------------------------

const SENT_AT_KEY = 'housetel.verifyEmail.sentAt'
/** Seconds before the same person can ask for another link (the backend also limits it per hour). */
export const RESEND_COOLDOWN = 60

function readSentAt(): number {
  try {
    return Number(window.sessionStorage.getItem(SENT_AT_KEY)) || 0
  } catch {
    return 0
  }
}

function markVerificationSent() {
  try {
    window.sessionStorage.setItem(SENT_AT_KEY, String(Date.now()))
  } catch {
    /* private mode: the cooldown just lives in this component */
  }
  window.dispatchEvent(new Event(SENT_AT_KEY))
}

/** Seconds left before "Resend link" is available again (0 = available). */
export function useResendCooldown(): number {
  const [sentAt, setSentAt] = useState(readSentAt)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const sync = () => {
      setSentAt(readSentAt())
      setNow(Date.now())
    }
    window.addEventListener(SENT_AT_KEY, sync)
    return () => window.removeEventListener(SENT_AT_KEY, sync)
  }, [])

  const remaining = Math.max(0, Math.ceil((sentAt + RESEND_COOLDOWN * 1000 - now) / 1000))
  useEffect(() => {
    if (remaining <= 0) return
    const id = window.setTimeout(() => setNow(Date.now()), 1000)
    return () => window.clearTimeout(id)
  }, [remaining, now])
  return remaining
}
