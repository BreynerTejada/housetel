import { CircleAlert, Clock, Lock, X, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'
import { Button } from '@/components/ui/button'
import { useActiveMembership } from '@/lib/auth'
import { formatMoney } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useBillingStatus, type OrganizationStatus } from '../api'

const BILLING_PATH = '/app/settings/billing'
const DISMISS_KEY = 'housetel.billingNotice.dismissed'

const CHIP: Record<Exclude<OrganizationStatus, 'active'>, { icon: LucideIcon; className: string }> = {
  trial: { icon: Clock, className: 'border-info/30 bg-info-soft text-info-ink' },
  past_due: { icon: CircleAlert, className: 'border-warning/35 bg-warning-soft text-warning-ink' },
  suspended: { icon: Lock, className: 'border-danger/35 bg-danger-soft text-danger-ink' },
  cancelled: { icon: CircleAlert, className: 'border-border bg-stone-soft text-stone-ink' },
}

function readDismissed(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY)
  } catch {
    return null
  }
}

/**
 * Topbar item (plan C11): the subscription state of the active organization. Active organizations show
 * nothing; a trial shows its days left; past due and suspended add a notice with the way out (pay).
 * The organization status comes from `Me`, so active hotels never make the extra request.
 */
export function BillingStatusItem() {
  const { t } = useTranslation('saas')
  const membership = useActiveMembership()
  const { pathname } = useLocation()
  const canView = useCan('saas.billing_view')
  const canManage = useCan('saas.billing_manage')
  const orgStatus = membership?.organization.status
  const orgId = membership?.organization.id ?? ''
  const status = useBillingStatus(Boolean(orgStatus && orgStatus !== 'active'))
  // The past-due notice can be hidden for the rest of the browser session (per organization).
  const [dismissedOrg, setDismissedOrg] = useState(readDismissed)
  const dismissed = dismissedOrg === orgId

  if (!orgStatus || orgStatus === 'active') return null
  const current = (status.data?.organization_status ?? orgStatus) as OrganizationStatus
  if (current === 'active') return null

  const chip = CHIP[current]
  const Icon = chip.icon
  const days = status.data?.trial_days_left
  const label =
    current === 'trial'
      ? days === null || days === undefined
        ? t('banner.chip.trialNoDays')
        : t('banner.chip.trial', { count: days })
      : t(`banner.chip.${current}`)
  const target = canView ? BILLING_PATH : '/app/getting-started'
  const onBillingPage = pathname.startsWith(BILLING_PATH)
  const alarming = current === 'past_due' || current === 'suspended'
  const showNotice = alarming && !onBillingPage && !(current === 'past_due' && dismissed)
  const amount = formatMoney(status.data?.open_balance ?? 0)
  // Suspended by the Housetel team with nothing to pay: explain it instead of asking for $ 0.
  const nothingDue = status.isSuccess && Number(status.data.open_balance) <= 0

  function dismiss() {
    setDismissedOrg(orgId)
    try {
      window.sessionStorage.setItem(DISMISS_KEY, orgId)
    } catch {
      /* private mode: the notice simply comes back on the next page load */
    }
  }

  return (
    <>
      <Link
        to={target}
        aria-label={label}
        title={label}
        className={cn(
          'h-8 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold whitespace-nowrap transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
          // Phones: a trial is not urgent (the checklist shows it); the rest collapses to its icon.
          current === 'trial' || current === 'cancelled' ? 'hidden sm:inline-flex' : 'inline-flex',
          chip.className,
        )}
      >
        <Icon aria-hidden className="size-3.5" />
        <span className={cn(alarming && 'hidden sm:inline')}>{label}</span>
      </Link>
      {showNotice &&
        createPortal(
          <section
            role="region"
            aria-label={t(`banner.notice.${current}.title`)}
            className={cn(
              'fixed inset-x-3 bottom-3 z-40 grid grid-cols-1 gap-3 rounded-xl border bg-surface p-4 shadow-lg sm:inset-x-auto sm:left-1/2 sm:w-[min(40rem,calc(100vw-2rem))] sm:-translate-x-1/2',
              'animate-pop-in sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center',
              current === 'suspended' ? 'border-danger/40' : 'border-warning/45',
            )}
          >
            <span
              aria-hidden
              className={cn(
                'hidden size-9 place-items-center rounded-lg sm:grid',
                current === 'suspended' ? 'bg-danger-soft text-danger-ink' : 'bg-warning-soft text-warning-ink',
              )}
            >
              <Icon className="size-[18px]" />
            </span>
            <div className="min-w-0 pr-7 sm:pr-0">
              <p className="font-bold text-fg">{t(`banner.notice.${current}.title`)}</p>
              <p className="mt-0.5 text-sm text-muted">
                {nothingDue && current === 'suspended'
                  ? t('banner.notice.suspended.byTeam')
                  : canManage
                    ? t(`banner.notice.${current}.owner`, { amount })
                    : t(`banner.notice.${current}.member`)}
              </p>
            </div>
            {canView && (
              <Button asChild variant={current === 'suspended' ? 'danger' : 'primary'} size="sm" className="justify-self-start sm:justify-self-end">
                <Link to={BILLING_PATH}>{canManage && !nothingDue ? t('banner.notice.pay') : t('banner.notice.see')}</Link>
              </Button>
            )}
            {current === 'past_due' && (
              <Button
                variant="ghost"
                size="icon-sm"
                className="absolute top-2 right-2"
                aria-label={t('banner.notice.dismiss')}
                onClick={dismiss}
              >
                <X aria-hidden />
              </Button>
            )}
          </section>,
          document.body,
        )}
    </>
  )
}
