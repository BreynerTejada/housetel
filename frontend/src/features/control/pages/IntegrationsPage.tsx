import { FlaskConical, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/utils'
import { useIntegrations, type Integration, type IntegrationMode } from '../api'
import { IntegrationCard } from '../components/IntegrationCard'
import { IntegrationSheet } from '../components/IntegrationSheet'
import { sortIntegrations } from '../lib/integrations'

/** `/app/settings/integrations`: one card per integration, the Real / Simulated switch and its credentials. */
export default function IntegrationsPage() {
  const { t } = useTranslation('control')
  const query = useIntegrations()
  const [editing, setEditing] = useState<{ kind: Integration['kind']; mode?: IntegrationMode } | null>(null)
  const items = useMemo(() => sortIntegrations(query.data ?? []), [query.data])
  // The sheet always shows the freshest copy of the integration (a test or a save replaces it in the cache).
  const current = editing ? (items.find((item) => item.kind === editing.kind) ?? null) : null

  return (
    <div className="grid gap-6">
      <PageHeader title={t('integrations.title')} description={t('integrations.description')} className="pb-0" />

      {query.isPending ? (
        <LoadingState variant="rows" rows={6} className="p-0" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <>
          <ModeBanner items={items} />
          <div className="grid gap-4 md:grid-cols-2">
            {items.map((integration) => (
              <IntegrationCard
                key={integration.kind}
                integration={integration}
                onConfigure={(item, mode) => setEditing({ kind: item.kind, mode })}
              />
            ))}
          </div>
        </>
      )}

      <IntegrationSheet
        integration={current}
        initialMode={editing?.mode}
        open={current !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
    </div>
  )
}

/**
 * How much of the hotel runs for real: one plate per integration (terracotta = real, hatched = simulated), with
 * the sentence that explains what "simulated" means for the people using it.
 */
function ModeBanner({ items }: { items: Integration[] }) {
  const { t } = useTranslation('control')
  const simulated = items.filter((item) => item.mode === 'simulated').length
  const allReal = simulated === 0
  const Icon = allReal ? Zap : FlaskConical

  return (
    <section
      aria-labelledby="integrations-mode-banner"
      className={cn(
        'grid gap-3 rounded-xl border p-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-4 sm:p-5',
        allReal ? 'border-accent/30 bg-accent-soft/50' : 'border-info/25 bg-info-soft/60',
      )}
    >
      <span
        className={cn(
          'grid size-10 place-items-center rounded-lg',
          allReal ? 'bg-accent-soft text-accent-ink' : 'bg-surface text-info-ink shadow-xs',
        )}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      <div className="grid min-w-0 gap-2">
        <h2 id="integrations-mode-banner" className="text-[15px] font-bold text-fg">
          {allReal ? t('integrations.banner.allReal') : t('integrations.banner.title', { count: simulated, total: items.length })}
        </h2>
        <p className="max-w-3xl text-[13px] text-fg/80">{allReal ? t('integrations.banner.bodyReal') : t('integrations.banner.body')}</p>
        <ul className="mt-1 flex flex-wrap gap-1.5" aria-label={t('integrations.banner.plates')}>
          {items.map((item) => {
            const real = item.mode === 'real'
            return (
              <li
                key={item.kind}
                title={`${t(`integrations.kinds.${item.kind}.title`)} · ${t(`integrations.mode.${item.mode}`)}`}
                className={cn(
                  'flex h-6 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-2xs font-semibold text-fg shadow-xs',
                  !item.enabled && 'opacity-50',
                )}
              >
                <span
                  aria-hidden
                  className={cn('size-2.5 shrink-0 rounded-[3px]', real ? 'bg-accent' : 'hatch border border-border-strong bg-surface-2')}
                />
                <span className="truncate">{t(`integrations.kinds.${item.kind}.short`)}</span>
                <span className="sr-only">: {t(`integrations.mode.${item.mode}`)}</span>
              </li>
            )
          })}
        </ul>
        <p aria-hidden className="flex items-center gap-3 text-2xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[3px] bg-accent" />
            {t('integrations.mode.real')}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="hatch size-2.5 rounded-[3px] border border-border-strong bg-surface-2" />
            {t('integrations.mode.simulated')}
          </span>
        </p>
      </div>
    </section>
  )
}
