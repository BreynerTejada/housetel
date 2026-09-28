import { useQueryClient } from '@tanstack/react-query'
import { CircleAlert, CircleCheck, LoaderCircle, X } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { paymentReturnParams, usePaymentStatus } from '@/features/finance/api'
import { cn } from '@/lib/utils'
import { portalKeys } from '../../api'

/**
 * Back from the gateway (`/g/<token>?paid=1&payment_ref=…`): confirms the payment with the server (finance
 * verifies with the provider) and refreshes the booking once it is approved.
 */
export function PaymentReturnBanner({ token }: { token: string }) {
  const { t } = useTranslation('guestportal')
  const { search, pathname } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { reference, transactionId } = paymentReturnParams(search)
  const payment = usePaymentStatus(reference, { transactionId })
  const status = payment.data?.status

  useEffect(() => {
    if (status === 'approved') void queryClient.invalidateQueries({ queryKey: portalKeys.portal(token) })
  }, [status, queryClient, token])

  if (!reference) return null
  const state = payment.isError ? 'error' : status === 'approved' ? 'approved' : status && ['declined', 'expired', 'error'].includes(status) ? status : 'checking'
  const good = state === 'approved'
  const waiting = state === 'checking'
  const Icon = waiting ? LoaderCircle : good ? CircleCheck : CircleAlert

  return (
    <div
      role="status"
      className={cn(
        'flex items-start gap-3 rounded-xl border px-4 py-3 text-sm',
        good ? 'border-transparent bg-success-soft text-success-ink' : waiting ? 'border-border bg-surface' : 'border-transparent bg-warning-soft text-warning-ink',
      )}
    >
      <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', waiting && 'animate-spin')} />
      <p className="flex-1 font-semibold">{t(`payment.${state}`)}</p>
      {!waiting && (
        <button
          type="button"
          aria-label={t('common:actions.close')}
          onClick={() => navigate(pathname, { replace: true })}
          className="rounded p-0.5 opacity-70 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
        >
          <X aria-hidden className="size-4" />
        </button>
      )}
    </div>
  )
}
