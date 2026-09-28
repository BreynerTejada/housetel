import { ArrowRight, FlaskConical } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useCan } from '@/lib/permissions'
import { isDemoEnvironment, useRuntimeConfig } from '@/lib/runtime'

/**
 * Slim, hatched strip above the staff topbar while the installation runs with simulations on outside
 * production (plan P1). The hatch is the same one the calendar uses for out-of-service rooms: "not the real
 * thing". It scrolls away with the page (the topbar stays sticky). Whoever manages integrations gets the way
 * out: the integrations page.
 */
export function DemoBanner() {
  const { t } = useTranslation()
  const config = useRuntimeConfig()
  const canManageIntegrations = useCan('control.integrations')
  if (!config.loaded || !isDemoEnvironment(config)) return null

  return (
    <div role="note" aria-label={t('demoBanner.label')} className="hatch border-b border-border bg-surface-2">
      <div className="flex min-h-8 items-center gap-2 px-3 py-1 text-xs text-muted sm:px-4 lg:px-6">
        <FlaskConical aria-hidden className="size-3.5 shrink-0 text-subtle" />
        <p className="min-w-0 flex-1 truncate">
          <span className="font-bold text-fg">{t('demoBanner.label')}</span>
          <span className="hidden sm:inline">
            <span aria-hidden className="mx-1.5 text-subtle">
              ·
            </span>
            <span className="hidden lg:inline">{t('demoBanner.detail')}</span>
            <span className="lg:hidden">{t('demoBanner.short')}</span>
          </span>
        </p>
        {canManageIntegrations && (
          <Link
            to="/app/settings/integrations"
            className="inline-flex shrink-0 items-center gap-1 rounded-sm font-semibold text-accent-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            <span className="hidden sm:inline">{t('demoBanner.cta')}</span>
            <span className="sm:hidden">{t('demoBanner.ctaShort')}</span>
            <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        )}
      </div>
    </div>
  )
}
