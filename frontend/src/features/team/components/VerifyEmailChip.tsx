import { MailWarning } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMe } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { isEmailUnverified } from '../account-api'
import { ResendVerificationButton } from './ResendVerificationButton'

const ACCOUNT_PATH = '/app/settings/account'

/**
 * Topbar item (P2): "Verify your email" while the signed-in user has not confirmed their address. The
 * popover resends the link without leaving the page. Nothing renders once the email is verified.
 */
export function VerifyEmailChip() {
  const { t } = useTranslation('team')
  const { data: me } = useMe()
  const [open, setOpen] = useState(false)
  if (!me || !isEmailUnverified(me)) return null
  const label = t('chip.label')

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          title={label}
          className={cn(
            'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-warning/35 bg-warning-soft px-2.5 text-xs font-semibold whitespace-nowrap text-warning-ink transition-colors',
            'hover:border-warning/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
          )}
        >
          <MailWarning aria-hidden className="size-3.5" />
          {/* Phones: only the icon (the popover explains it). */}
          <span className="hidden sm:inline">{label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(21rem,calc(100vw-1.5rem))] p-4">
        <p className="font-bold text-fg">{t('chip.title')}</p>
        <p className="mt-1 text-sm break-words text-muted">{t('chip.text', { email: me.email })}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <ResendVerificationButton variant="primary" size="sm" />
          <Button asChild variant="ghost" size="sm">
            <Link to={ACCOUNT_PATH} onClick={() => setOpen(false)}>
              {t('chip.account')}
            </Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
