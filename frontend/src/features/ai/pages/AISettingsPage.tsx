import { Activity, Bot, Cpu, Timer, TriangleAlert } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { KpiTile } from '@/components/KpiTile'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatNumber, formatRelative, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useAISettings, useUpdateAISettings, useUsage, type AISettings, type AISettingsInput, type Lang, type ProviderInfo } from '../api'

/** `/app/settings/ai`: which engine answers (real or simulated), the hotel's AI features and their usage. */
export default function AISettingsPage() {
  const { t } = useTranslation('ai')
  const settings = useAISettings()

  return (
    <div className="grid gap-6">
      <PageHeader title={t('settings.title')} description={t('settings.description')} className="pb-0" />
      {settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : settings.isPending ? (
        <LoadingState />
      ) : (
        <>
          <StatusCard provider={settings.data.provider} />
          <div className="grid gap-6 lg:grid-cols-2">
            <ProviderCard key={`${settings.data.provider.mode}-${settings.data.provider.provider}-${settings.data.provider.custom_model}`} settings={settings.data} />
            <FeaturesCard settings={settings.data} />
          </div>
          <GreetingCard key={JSON.stringify(settings.data.chatbot_greeting)} settings={settings.data} />
          <UsageCard />
        </>
      )}
    </div>
  )
}

/** What really answers right now: the one thing an owner needs to know about the AI. */
function StatusCard({ provider }: { provider: ProviderInfo }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const real = provider.effective === 'real'
  const problem = provider.status?.error
  const noKey = provider.mode === 'real' && !real
  return (
    <Card className={cn('border-l-4', real ? 'border-l-success' : 'border-l-warning')}>
      <CardContent className="flex flex-wrap items-start gap-4 py-4">
        <span
          aria-hidden
          className={cn(
            'mt-1.5 size-2.5 shrink-0 rounded-full',
            real ? 'bg-success shadow-[0_0_0_4px_var(--success-soft)]' : 'bg-warning shadow-[0_0_0_4px_var(--warning-soft)]',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="eyebrow">{t('settings.status')}</p>
          <p className="mt-0.5 text-[17px] leading-6 font-bold text-fg">
            {real ? t('settings.effectiveReal', { provider: provider.label }) : t('settings.effectiveSimulated')}
          </p>
          <p className="mt-0.5 text-[13px] text-muted">
            {real ? t('settings.modelInUse', { model: provider.model }) : noKey ? t('settings.noKey') : t('settings.simulatedText')}
          </p>
          {problem && (
            <p className="mt-2 flex items-start gap-1.5 text-[13px] text-warning-ink">
              <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              <span>
                {t('settings.lastError', { error: problem })}
                {provider.status.at && <span className="text-muted"> · {formatRelative(provider.status.at, lang)}</span>}
              </span>
            </p>
          )}
          {!problem && provider.status?.last_success_at && real && (
            <p className="mt-2 text-[13px] text-success-ink">{t('settings.recovered', { when: formatRelative(provider.status.last_success_at, lang) })}</p>
          )}
        </div>
        <p className="w-full text-xs text-subtle sm:w-auto sm:max-w-xs">{t('settings.providerText')}</p>
      </CardContent>
    </Card>
  )
}

function useSave() {
  const { t } = useTranslation('ai')
  const update = useUpdateAISettings()
  return {
    ...update,
    save: (input: AISettingsInput, message = t('settings.saved')) =>
      update.mutateAsync(input).then(
        () => toast.success(message),
        (error) => toast.error(errorMessage(error, t)),
      ),
  }
}

function ProviderCard({ settings }: { settings: AISettings }) {
  const { t } = useTranslation('ai')
  const canEdit = useCan('ai.settings')
  const info = settings.provider
  const [mode, setMode] = useState(info.mode)
  const [provider, setProvider] = useState(info.provider)
  const [model, setModel] = useState(info.custom_model)
  const update = useSave()
  const modeId = useId()
  const providerId = useId()
  const modelId = useId()
  const chosen = info.providers.find((item) => item.value === provider)
  const hasKey = Boolean(chosen?.platform_key_configured) || (provider === info.provider && info.own_key_configured)
  const dirty = mode !== info.mode || provider !== info.provider || model.trim() !== info.custom_model

  function submit(event: FormEvent) {
    event.preventDefault()
    void update.save({ mode, provider, model: model.trim() })
  }

  return (
    <Card>
      <form onSubmit={submit} className="flex h-full flex-col">
        <CardHeader>
          <CardTitle>{t('settings.provider')}</CardTitle>
          <CardDescription>{t('settings.providerHint')}</CardDescription>
        </CardHeader>
        <CardContent className="grid flex-1 gap-4">
          <div className="grid gap-1.5">
            <Label id={modeId}>{t('settings.mode')}</Label>
            <ToggleGroup
              type="single"
              aria-labelledby={modeId}
              value={mode}
              disabled={!canEdit}
              onValueChange={(value) => value && setMode(value as ProviderInfo['mode'])}
              className="w-fit"
            >
              <ToggleGroupItem value="real">{t('settings.modeReal')}</ToggleGroupItem>
              <ToggleGroupItem value="simulated">{t('settings.modeSimulated')}</ToggleGroupItem>
            </ToggleGroup>
            <p className="text-xs text-muted">{mode === 'real' ? t('settings.modeRealHint') : t('settings.modeSimulatedHint')}</p>
          </div>
          <div className={cn('grid gap-4 sm:grid-cols-2', mode === 'simulated' && 'opacity-60')}>
            <div className="grid content-start gap-1.5">
              <Label htmlFor={providerId}>{t('settings.providerLabel')}</Label>
              <Select name="provider" value={provider} disabled={!canEdit || mode === 'simulated'} onValueChange={(value) => setProvider(value as ProviderInfo['provider'])}>
                <SelectTrigger id={providerId}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {info.providers.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className={cn('text-xs', hasKey ? 'text-success-ink' : 'text-warning-ink')}>
                {hasKey ? t('settings.platformKey') : t('settings.noPlatformKey')}
              </p>
            </div>
            <div className="grid content-start gap-1.5">
              <Label htmlFor={modelId}>{t('settings.model')}</Label>
              <Input
                id={modelId}
                name="model"
                value={model}
                maxLength={100}
                disabled={!canEdit || mode === 'simulated'}
                placeholder={provider === info.provider ? info.platform_model : t('settings.modelPlaceholder')}
                onChange={(event) => setModel(event.target.value)}
                className="num"
              />
              <p className="text-xs text-muted">{t('settings.modelHint')}</p>
            </div>
          </div>
          <p className="text-xs text-muted">
            {info.own_key_configured ? t('settings.ownKey') : t('settings.ownKeyHint')}{' '}
            <Link to="/app/settings/integrations" className="font-semibold text-accent-ink hover:underline">
              {t('settings.goIntegrations')}
            </Link>
          </p>
        </CardContent>
        {canEdit && (
          <CardFooter className="justify-end">
            <Button type="submit" variant="primary" size="sm" disabled={!dirty} loading={update.isPending}>
              {t('settings.save')}
            </Button>
          </CardFooter>
        )}
      </form>
    </Card>
  )
}

const FEATURES = [
  { key: 'copilot_enabled', label: 'settings.copilot', hint: 'settings.copilotHint' },
  { key: 'chatbot_enabled', label: 'settings.chatbotFeature', hint: 'settings.chatbotHint' },
  { key: 'draft_replies_enabled', label: 'settings.drafts', hint: 'settings.draftsHint' },
] as const

function FeaturesCard({ settings }: { settings: AISettings }) {
  const { t } = useTranslation('ai')
  const canEdit = useCan('ai.settings')
  const update = useSave()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.features')}</CardTitle>
        <CardDescription>{t('settings.featuresHint')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid divide-y divide-border">
          {FEATURES.map(({ key, label, hint }) => (
            <FeatureRow
              key={key}
              label={t(label)}
              hint={t(hint)}
              checked={settings[key]}
              disabled={!canEdit || (update.isPending && key in (update.variables ?? {}))}
              onCheckedChange={(checked) => void update.save({ [key]: checked })}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function FeatureRow({
  label,
  hint,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string
  hint: string
  checked: boolean
  disabled: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  const id = useId()
  const hintId = useId()
  return (
    <li className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <Label htmlFor={id} className="text-sm">
          {label}
        </Label>
        <p id={hintId} className="text-[13px] text-muted">
          {hint}
        </p>
      </div>
      <Switch id={id} aria-describedby={hintId} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </li>
  )
}

function GreetingCard({ settings }: { settings: AISettings }) {
  const { t } = useTranslation('ai')
  const canEdit = useCan('ai.settings')
  const [greeting, setGreeting] = useState<Record<Lang, string>>({ es: settings.chatbot_greeting.es ?? '', en: settings.chatbot_greeting.en ?? '' })
  const update = useSave()
  const dirty = greeting.es !== (settings.chatbot_greeting.es ?? '') || greeting.en !== (settings.chatbot_greeting.en ?? '')
  const fields: { lang: Lang; label: string }[] = [
    { lang: 'es', label: t('settings.greetingEs') },
    { lang: 'en', label: t('settings.greetingEn') },
  ]
  return (
    <Card>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void update.save({ chatbot_greeting: { es: greeting.es.trim(), en: greeting.en.trim() } }, t('settings.greetingSaved'))
        }}
      >
        <CardHeader>
          <CardTitle>{t('settings.greeting')}</CardTitle>
          <CardDescription>{t('settings.greetingHint')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {fields.map(({ lang, label }) => (
            <GreetingField
              key={lang}
              label={label}
              lang={lang}
              value={greeting[lang]}
              disabled={!canEdit}
              onChange={(value) => setGreeting((current) => ({ ...current, [lang]: value }))}
            />
          ))}
        </CardContent>
        {canEdit && (
          <CardFooter className="justify-end">
            <Button type="submit" size="sm" variant="primary" disabled={!dirty} loading={update.isPending}>
              {t('settings.save')}
            </Button>
          </CardFooter>
        )}
      </form>
    </Card>
  )
}

function GreetingField({
  label,
  lang,
  value,
  disabled,
  onChange,
}: {
  label: string
  lang: Lang
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const { t } = useTranslation('ai')
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={`greeting-${lang}`}
        lang={lang}
        value={value}
        maxLength={300}
        disabled={disabled}
        placeholder={t('settings.greetingPlaceholder')}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}

function UsageCard() {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const usage = useUsage(30)

  let content: ReactNode
  if (usage.isError) content = <ErrorState error={usage.error} onRetry={() => void usage.refetch()} />
  else if (usage.isPending) content = <LoadingState />
  else {
    const report = usage.data
    const totals = report.totals
    const trend = report.by_day.slice(-12).map((day) => ({ label: formatDate(day.date, 'd MMM', lang), value: day.calls }))
    content =
      totals.calls === 0 ? (
        <p className="py-6 text-center text-sm text-muted">{t('settings.usageEmpty')}</p>
      ) : (
        <div className="grid gap-6">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <KpiTile label={t('settings.calls')} value={formatNumber(totals.calls, lang, 0)} trend={trend.length > 1 ? trend : undefined} icon={Activity} intent="neutral" />
            <KpiTile label={t('settings.realCalls')} value={formatNumber(totals.real, lang, 0)} icon={Cpu} intent="neutral" />
            <KpiTile label={t('settings.simulatedCalls')} value={formatNumber(totals.simulated, lang, 0)} icon={Bot} intent="neutral" />
            <KpiTile
              label={t('settings.latency')}
              value={totals.real ? `${formatNumber(totals.avg_latency_ms / 1000, lang, 1)} s` : '—'}
              icon={Timer}
              intent="neutral"
            />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="grid content-start gap-2">
              <p className="text-[13px] font-semibold text-fg">{t('settings.byFeature')}</p>
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted">
                    <th scope="col" className="py-1.5 font-semibold">
                      {t('settings.feature')}
                    </th>
                    <th scope="col" className="py-1.5 text-right font-semibold">
                      {t('settings.calls')}
                    </th>
                    <th scope="col" className="py-1.5 text-right font-semibold">
                      {t('settings.simulatedShort')}
                    </th>
                    <th scope="col" className="py-1.5 text-right font-semibold">
                      {t('settings.errors')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_feature.map((row) => (
                    <tr key={row.feature} className="border-b border-border/60 last:border-0">
                      <td className="py-2 text-fg">{t(`settings.featureNames.${row.feature}`, { defaultValue: row.feature })}</td>
                      <td className="num py-2 text-right">{formatNumber(row.calls, lang, 0)}</td>
                      <td className="num py-2 text-right text-muted">{formatNumber(row.simulated, lang, 0)}</td>
                      <td className={cn('num py-2 text-right', row.errors ? 'text-danger-ink' : 'text-muted')}>{formatNumber(row.errors, lang, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-subtle">
                {t('settings.tokensValue', { input: formatNumber(totals.input_tokens, lang, 0), output: formatNumber(totals.output_tokens, lang, 0) })}
              </p>
            </div>
            <div className="grid content-start gap-2">
              <p className="text-[13px] font-semibold text-fg">{t('settings.recentErrors')}</p>
              {report.recent_errors.length === 0 ? (
                <p className="text-[13px] text-muted">{t('settings.noErrors')}</p>
              ) : (
                <ul className="grid gap-2">
                  {report.recent_errors.map((item) => (
                    <li key={`${item.at}-${item.feature}`} className="rounded-md bg-surface-2 px-3 py-2 text-[12.5px]">
                      <p className="flex flex-wrap items-center gap-x-2 text-muted">
                        <Badge tone="neutral">{t(`settings.featureNames.${item.feature}`, { defaultValue: item.feature })}</Badge>
                        <span>{formatRelative(item.at, lang)}</span>
                      </p>
                      <p className="mt-1 line-clamp-2 break-words text-fg">{item.error}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.usage')}</CardTitle>
        <CardDescription>{t('settings.usageHint')}</CardDescription>
      </CardHeader>
      <CardContent>{content}</CardContent>
    </Card>
  )
}
