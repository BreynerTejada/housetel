import { FlaskConical, PlugZap, Settings2, Zap } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useTestIntegration, useUpdateIntegration, type Integration, type IntegrationMode } from '../api'
import { IntegrationIcon } from './badges'
import { IntegrationStatusPill } from './IntegrationStatusPill'

interface Props {
  integration: Integration
  /** Opens the configuration sheet, optionally preselecting a mode (switching to real always goes there). */
  onConfigure: (integration: Integration, mode?: IntegrationMode) => void
}

/**
 * One integration of the hotel: what it does, its mode (the Real / Simulated switch), its connection state and
 * the two things people do with it — test the connection and configure it.
 */
export function IntegrationCard({ integration, onConfigure }: Props) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const update = useUpdateIntegration()
  const test = useTestIntegration()
  const kindText = (key: string) => t(`integrations.kinds.${integration.kind}.${key}`)
  const title = kindText('title')
  const real = integration.mode === 'real'
  const provider = integration.providers[integration.mode]
  const providerName = provider ? (lang === 'en' && provider.label_en ? provider.label_en : provider.label) : ''

  async function changeMode(next: string) {
    if (next !== 'real' && next !== 'simulated') return // radix clears the value when the active item is clicked
    if (next === integration.mode) return
    if (next === 'real') {
      onConfigure(integration, 'real')
      return
    }
    try {
      await update.mutateAsync({ kind: integration.kind, body: { mode: 'simulated' } })
      toast.success(t('integrations.toasts.simulated', { name: title }))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  async function runTest() {
    try {
      const result = await test.mutateAsync(integration.kind)
      if (result.test?.ok) toast.success(t('integrations.toasts.testOk', { message: result.test.message }))
      else toast.error(t('integrations.toasts.testError', { message: result.test?.message ?? '' }))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        'flex min-w-0 flex-col rounded-xl border bg-surface shadow-xs transition-colors',
        real ? 'border-accent/35' : 'border-border',
        !integration.enabled && 'bg-surface-2/60',
      )}
    >
      <div className="flex items-start gap-3 p-4 pb-3 sm:p-5 sm:pb-3">
        <IntegrationIcon kind={integration.kind} real={real} className={cn(!integration.enabled && 'opacity-60')} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
            <h2 id={titleId} className="text-[15px] leading-5 font-bold text-fg">
              {title}
            </h2>
            <IntegrationStatusPill integration={integration} />
          </div>
          <p className="mt-1 text-[13px] text-muted">{kindText('description')}</p>
        </div>
      </div>

      <div className="grid gap-2 px-4 pb-4 sm:px-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="eyebrow" id={`${titleId}-mode`}>
            {t('integrations.mode.label')}
          </span>
          <ToggleGroup
            type="single"
            value={integration.mode}
            onValueChange={(value) => void changeMode(value)}
            aria-labelledby={`${titleId}-mode`}
            disabled={update.isPending}
          >
            {(['real', 'simulated'] as const).map((mode) => {
              const Icon = mode === 'real' ? Zap : FlaskConical
              const available = integration.available_modes.includes(mode)
              return (
                <ToggleGroupItem
                  key={mode}
                  value={mode}
                  disabled={!available}
                  title={available ? undefined : t('integrations.mode.unavailable')}
                  className={cn(mode === 'real' && 'data-[state=on]:text-accent-ink')}
                >
                  <Icon aria-hidden />
                  {t(`integrations.mode.${mode}`)}
                </ToggleGroupItem>
              )
            })}
          </ToggleGroup>
        </div>
        <p className="text-[13px] text-fg/85">
          {kindText(integration.mode)}
          {providerName && real && <span className="text-muted"> · {t('integrations.card.provider', { name: providerName })}</span>}
        </p>
        {integration.status === 'error' && integration.status_message && (
          <p className="line-clamp-2 rounded-md bg-danger-soft px-2.5 py-1.5 text-xs break-words text-danger-ink">{integration.status_message}</p>
        )}
      </div>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3 sm:px-5">
        {integration.last_checked_at && (
          <p className="min-w-[10rem] flex-1 truncate text-xs text-muted" title={integration.status_message || undefined}>
            {t('integrations.status.checked', { when: formatRelative(integration.last_checked_at, lang) })}
          </p>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => void runTest()} loading={test.isPending} disabled={!integration.enabled}>
            {!test.isPending && <PlugZap aria-hidden />}
            {test.isPending ? t('integrations.card.testing') : t('integrations.card.test')}
          </Button>
          <Button size="sm" onClick={() => onConfigure(integration)}>
            <Settings2 aria-hidden />
            {t('integrations.card.configure')}
          </Button>
        </div>
      </div>
    </article>
  )
}
