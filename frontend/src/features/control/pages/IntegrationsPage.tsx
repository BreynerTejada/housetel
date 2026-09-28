import { ArrowRight, FlaskConical, Wrench, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useIntegrations, type Integration, type IntegrationMode } from '../api'
import { IntegrationCard } from '../components/IntegrationCard'
import { IntegrationSheet } from '../components/IntegrationSheet'
import { needsCredentials, sortIntegrations } from '../lib/integrations'

interface Editing {
  kind: Integration['kind']
  mode?: IntegrationMode
  /** Opened to read the provider's guide (card button or the banner). */
  guide?: boolean
}

/** `/app/settings/integrations`: one card per integration, the Real / Simulated switch, its guide and credentials. */
export default function IntegrationsPage() {
  const { t } = useTranslation('control')
  const query = useIntegrations()
  const [editing, setEditing] = useState<Editing | null>(null)
  const items = useMemo(() => sortIntegrations(query.data ?? []), [query.data])
  // The sheet always shows the freshest copy of the integration (a test or a save replaces it in the cache).
  const current = editing ? (items.find((item) => item.kind === editing.kind) ?? null) : null
  const openGuide = (item: Integration) => setEditing({ kind: item.kind, mode: 'real', guide: true })

  return (
    <div className="grid gap-6">
      <PageHeader title={t('integrations.title')} description={t('integrations.description')} className="pb-0" />

      {query.isPending ? (
        <LoadingState variant="rows" rows={6} className="p-0" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <>
          <ModeBanner items={items} onGuide={openGuide} />
          <div className="grid gap-4 md:grid-cols-2">
            {items.map((integration) => (
              <IntegrationCard
                key={integration.kind}
                integration={integration}
                onConfigure={(item, mode) => setEditing({ kind: item.kind, mode })}
                onGuide={openGuide}
              />
            ))}
          </div>
        </>
      )}

      <IntegrationSheet
        integration={current}
        initialMode={editing?.mode}
        focusGuide={editing?.guide ?? false}
        open={current !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
    </div>
  )
}

/**
 * The call to action of the page (plan P6): how many integrations still run simulated, "Activa los modos reales"
 * and a button to the first guide. Below, the hotel's key rack — one tag per integration (terracotta = real,
 * hatched = simulated, ringed = real but its credentials are missing); each tag opens its guide.
 */
function ModeBanner({ items, onGuide }: { items: Integration[]; onGuide: (item: Integration) => void }) {
  const { t } = useTranslation('control')
  const simulated = items.filter((item) => item.mode === 'simulated')
  // real mode but still without its credentials (in production every integration starts like this)
  const unfinished = items.filter(needsCredentials)
  const state = simulated.length > 0 ? 'simulated' : unfinished.length > 0 ? 'unfinished' : 'live'
  const next = state === 'simulated' ? simulated[0] : state === 'unfinished' ? unfinished[0] : null
  const Icon = state === 'live' ? Zap : state === 'unfinished' ? Wrench : FlaskConical
  const nextName = next ? t(`integrations.kinds.${next.kind}.title`) : ''

  return (
    <section
      aria-labelledby="integrations-mode-banner"
      className={cn(
        'grid gap-3 rounded-xl border p-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-4 sm:p-5',
        state === 'live' ? 'border-accent/30 bg-accent-soft/50' : 'border-info/25 bg-info-soft/60',
      )}
    >
      <span
        className={cn(
          'grid size-10 place-items-center rounded-lg',
          state === 'live' ? 'bg-accent-soft text-accent-ink' : 'bg-surface text-info-ink shadow-xs',
        )}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      <div className="grid min-w-0 gap-2">
        {state !== 'live' && (
          <p className="eyebrow text-info-ink">
            {state === 'simulated'
              ? t('integrations.banner.eyebrow', { count: simulated.length, total: items.length })
              : t('integrations.banner.eyebrowUnfinished', { count: unfinished.length })}
          </p>
        )}
        <h2 id="integrations-mode-banner" className="text-lg leading-6 font-extrabold tracking-[-0.01em] text-fg">
          {state === 'simulated' ? t('integrations.banner.cta') : state === 'unfinished' ? t('integrations.banner.ctaUnfinished') : t('integrations.banner.allReal')}
        </h2>
        <p className="max-w-3xl text-[13px] text-fg/80">
          {state === 'simulated' ? t('integrations.banner.body') : state === 'unfinished' ? t('integrations.banner.bodyUnfinished') : t('integrations.banner.bodyReal')}
        </p>
        {next && (
          <Button variant="primary" size="sm" className="mt-1 w-fit" onClick={() => onGuide(next)}>
            {state === 'simulated' ? t('integrations.banner.start', { name: nextName }) : t('integrations.banner.continue', { name: nextName })}
            <ArrowRight aria-hidden />
          </Button>
        )}
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={t('integrations.banner.plates')}>
          {items.map((item) => {
            const real = item.mode === 'real'
            const pending = needsCredentials(item)
            const name = t(`integrations.kinds.${item.kind}.title`)
            const status = pending ? t('integrations.banner.pending') : t(`integrations.mode.${item.mode}`)
            return (
              <li key={item.kind}>
                <button
                  type="button"
                  onClick={() => onGuide(item)}
                  title={`${name} · ${status}`}
                  aria-label={t('integrations.banner.plateLabel', { name, status })}
                  className={cn(
                    'flex h-7 items-center gap-1.5 rounded-md border bg-surface px-2 text-2xs font-semibold text-fg shadow-xs transition-colors',
                    'hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                    pending ? 'border-warning/60' : 'border-border',
                    !item.enabled && !pending && 'opacity-60',
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      'size-2.5 shrink-0 rounded-[3px]',
                      real ? 'bg-accent' : 'hatch border border-border-strong bg-surface-2',
                      pending && 'ring-2 ring-warning/50',
                    )}
                  />
                  <span className="truncate">{t(`integrations.kinds.${item.kind}.short`)}</span>
                </button>
              </li>
            )
          })}
        </ul>
        <p aria-hidden className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[3px] bg-accent" />
            {t('integrations.mode.real')}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="hatch size-2.5 rounded-[3px] border border-border-strong bg-surface-2" />
            {t('integrations.mode.simulated')}
          </span>
          {unfinished.length > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-[3px] bg-accent ring-2 ring-warning/50" />
              {t('integrations.banner.pending')}
            </span>
          )}
          <span>{t('integrations.banner.tapHint')}</span>
        </p>
      </div>
    </section>
  )
}
