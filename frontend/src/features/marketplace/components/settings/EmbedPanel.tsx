import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { isApiError } from '@/lib/api'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { getActivePromoCodes, getEmbedSnippet, marketplaceKeys, type EngineSettings } from '../../api'
import { moneyLabel } from '../../lib/text'
import { CopyBlock, SettingsSection } from './SettingsBits'

/** Links and HTML to put the booking engine on the hotel's own website, a live preview, and the promo codes. */
export function EmbedPanel({ settings }: { settings: EngineSettings }) {
  const { t, i18n } = useTranslation('marketplace')
  const lang = normalizeLang(i18n.language)
  const snippet = useQuery({ queryKey: marketplaceKeys.embedSnippet, queryFn: getEmbedSnippet })
  // Promo codes live in rates (`rates.view`): without that permission the block just stays hidden.
  const promos = useQuery({ queryKey: marketplaceKeys.promoCodes, queryFn: getActivePromoCodes, retry: false })
  const promosForbidden = isApiError(promos.error) && promos.error.status === 403

  if (snippet.isPending) return <LoadingState />
  if (snippet.isError) return <ErrorState error={snippet.error} onRetry={() => void snippet.refetch()} />

  return (
    <div className="min-w-0">
      <SettingsSection title={t('settings.embed.links')}>
        <CopyBlock label={t('settings.embed.engineUrl')} value={snippet.data.engine_url} />
        <CopyBlock label={t('settings.embed.embedUrl')} value={snippet.data.embed_url} />
      </SettingsSection>
      <SettingsSection title={t('settings.embed.iframe')} hint={t('settings.embed.iframeHint')}>
        <CopyBlock label={t('settings.embed.iframe')} value={snippet.data.iframe} code />
        <div className="grid gap-2">
          <p className="text-[13px] font-semibold text-fg">{t('settings.embed.preview')}</p>
          <div className="overflow-hidden rounded-xl border border-dashed border-border-strong bg-surface-2 p-3">
            <iframe src={snippet.data.embed_url} title={t('settings.embed.preview')} loading="lazy" className="h-[220px] w-full max-w-[980px] rounded-[14px] border-0 bg-surface" />
          </div>
        </div>
      </SettingsSection>
      <SettingsSection title={t('settings.embed.button')} hint={t('settings.embed.buttonHint')}>
        <CopyBlock label={t('settings.embed.button')} value={snippet.data.button} code />
        <div>
          <Button asChild variant="secondary" size="sm">
            <a href={snippet.data.engine_url} target="_blank" rel="noopener noreferrer">
              {t('settings.embed.open')}
              <ExternalLink aria-hidden />
            </a>
          </Button>
        </div>
      </SettingsSection>
      {!promosForbidden && (
        <SettingsSection title={t('settings.embed.promos')} hint={settings.show_promo_field ? t('settings.embed.promosHint') : t('settings.embed.promosHidden')}>
          {promos.isPending ? (
            <LoadingState variant="rows" rows={2} className="p-0" />
          ) : promos.isError ? (
            <ErrorState error={promos.error} onRetry={() => void promos.refetch()} className="py-4" />
          ) : promos.data.results.length === 0 ? (
            <p className="text-sm text-muted">{t('settings.embed.noPromos')}</p>
          ) : (
            <ul className="grid gap-2">
              {promos.data.results.map((promo) => (
                <li key={promo.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2">
                  <span className="num text-sm font-bold tracking-[0.04em] text-fg">{promo.code}</span>
                  <span className="text-sm text-muted">
                    {promo.discount_type === 'percent'
                      ? t('settings.embed.percentOff', { value: Number(promo.value) })
                      : t('settings.embed.amountOff', { value: moneyLabel(promo.value) })}
                    {promo.stay_from && promo.stay_to && ` · ${formatDateRange(promo.stay_from, promo.stay_to, lang)}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Button asChild variant="ghost" size="sm" className="w-fit -ml-3">
            <Link to="/app/rates/promos">{t('settings.embed.managePromos')}</Link>
          </Button>
        </SettingsSection>
      )}
    </div>
  )
}
