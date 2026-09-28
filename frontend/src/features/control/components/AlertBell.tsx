import { ArrowRight, Bell, Check, CircleCheck } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAlertCount, useResolveAlerts, type Alert } from '../api'
import { SeverityIcon } from './severity'

/**
 * Topbar bell: open alerts of the hotel (polled every minute). The badge turns clay when one is critical; the
 * popover lists the most severe ones with a shortcut to where each is fixed and a one-click "Resolver".
 */
export function AlertBell() {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const counts = useAlertCount()
  const resolve = useResolveAlerts()
  const total = counts.data?.open ?? 0
  const critical = counts.data?.by_severity.critical ?? 0
  const status = total ? t('bell.count', { count: total }) : t('bell.none')

  async function resolveOne(alert: Alert) {
    try {
      await resolve.mutateAsync([alert.id])
      toast.success(t('alerts.toasts.resolved'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`${t('bell.label')} · ${status}`} title={status}>
          <Bell aria-hidden />
          {total > 0 && (
            <span
              aria-hidden
              className={cn(
                'num absolute top-1 right-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] leading-none font-bold ring-2 ring-bg',
                critical > 0 ? 'bg-danger text-on-accent' : 'bg-accent text-on-accent',
              )}
            >
              {total > 99 ? '99+' : total}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-1.5rem))] p-0">
        <div className="flex items-baseline justify-between gap-3 border-b border-border px-4 py-3">
          <p className="text-sm font-bold text-fg">{t('bell.label')}</p>
          <p className="num text-xs text-muted">{status}</p>
        </div>
        {counts.data && counts.data.latest.length > 0 ? (
          <ul className="max-h-[min(24rem,60dvh)] divide-y divide-border overflow-y-auto">
            {counts.data.latest.map((alert) => (
              <li key={alert.id} className="flex items-start gap-3 px-4 py-3">
                <SeverityIcon severity={alert.severity} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  {alert.link ? (
                    <Link
                      to={alert.link}
                      onClick={() => setOpen(false)}
                      className="line-clamp-2 rounded-sm text-[13px] leading-5 font-semibold text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      {alert.title}
                    </Link>
                  ) : (
                    <p className="line-clamp-2 text-[13px] leading-5 font-semibold text-fg">{alert.title}</p>
                  )}
                  <p className="mt-0.5 text-xs text-muted">{formatRelative(alert.updated_at, lang)}</p>
                </div>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => void resolveOne(alert)}
                  disabled={resolve.isPending}
                  aria-label={t('bell.resolve', { title: alert.title })}
                  title={t('alerts.resolve')}
                >
                  <Check aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex flex-col items-center gap-1 px-4 py-8 text-center">
            <CircleCheck aria-hidden className="size-6 text-success-ink" />
            <p className="mt-1 text-sm font-semibold text-fg">{t('bell.allClear')}</p>
            <p className="text-xs text-muted">{t('bell.allClearHint')}</p>
          </div>
        )}
        <div className="border-t border-border p-2">
          <Button asChild variant="ghost" size="sm" className="w-full justify-between">
            <Link to="/app/alerts" onClick={() => setOpen(false)}>
              {t('bell.viewAll')}
              <ArrowRight aria-hidden />
            </Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
