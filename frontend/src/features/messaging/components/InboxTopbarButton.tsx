import { Inbox } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useUnreadCount } from '../api'

/** Topbar: the inbox, with the number of threads waiting for an answer (polled every minute). */
export function InboxTopbarButton() {
  const { t } = useTranslation('messaging')
  const unread = useUnreadCount()
  const count = unread.data?.conversations ?? 0
  const status = count ? t('topbar.waiting', { count }) : t('topbar.none')

  return (
    <Tooltip content={status}>
      <Button asChild variant="ghost" size="icon" className="relative">
        <Link to={count ? '/app/inbox?view=unread' : '/app/inbox'} aria-label={`${t('topbar.label')} · ${status}`}>
          <Inbox aria-hidden />
          {count > 0 && (
            <span
              aria-hidden
              className="num absolute top-1 right-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] leading-none font-bold text-on-accent ring-2 ring-bg"
            >
              {count > 99 ? '99+' : count}
            </span>
          )}
        </Link>
      </Button>
    </Tooltip>
  )
}
