import { ArrowUpRight, FlaskConical, PlugZap, TriangleAlert, Zap } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { usePermissionChecker } from '@/lib/permissions'
import { useRuntimeConfig } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import {
  useTestIntegration,
  useUpdateIntegration,
  type ConfigField,
  type ConfigValue,
  type Integration,
  type IntegrationMode,
  type IntegrationUpdate,
} from '../api'
import { guideFor } from '../lib/guides'
import { allowedModes, isLive, KIND_META } from '../lib/integrations'
import { IntegrationIcon } from './badges'
import { ConfigFieldInput } from './ConfigFieldInput'
import { IntegrationGuide } from './IntegrationGuide'
import { IntegrationStatusPill } from './IntegrationStatusPill'

interface Props {
  integration: Integration | null
  /** Mode preselected when the sheet opens (e.g. the user clicked "Real" on the card). */
  initialMode?: IntegrationMode
  /** Opened from the card's "Guía" button: the step-by-step guide starts open and in view. */
  focusGuide?: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Configuration of one integration: mode, the provider's step-by-step guide to real mode (plan P6), its form
 * (from its CONFIG_FIELDS, each value with where it lives in the provider's panel), on/off and a test.
 */
export function IntegrationSheet({ integration, initialMode, focusGuide = false, open, onOpenChange }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[min(34rem,100vw)]">
        {integration && (
          <IntegrationForm
            // a new form per integration and preselected mode; tests and saves refresh `integration` in place
            key={`${integration.kind}:${initialMode ?? integration.mode}:${focusGuide ? 'guide' : 'form'}`}
            integration={integration}
            initialMode={initialMode ?? integration.mode}
            focusGuide={focusGuide}
            onClose={() => onOpenChange(false)}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

function initialValues(fields: ConfigField[], config: Record<string, ConfigValue>): Record<string, ConfigValue> {
  const values: Record<string, ConfigValue> = {}
  for (const field of fields) {
    if (field.secret) continue
    values[field.name] = config[field.name] ?? null
  }
  return values
}

function IntegrationForm({
  integration,
  initialMode,
  focusGuide,
  onClose,
}: {
  integration: Integration
  initialMode: IntegrationMode
  focusGuide: boolean
  onClose: () => void
}) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const can = usePermissionChecker()
  const update = useUpdateIntegration()
  const test = useTestIntegration()
  const { simulations_enabled: simulations } = useRuntimeConfig()
  const kindText = (key: string) => t(`integrations.kinds.${integration.kind}.${key}`)
  const title = kindText('title')
  const meta = KIND_META[integration.kind] ?? {}
  const modes = allowedModes(integration, simulations)
  const guide = guideFor(integration.kind, lang)
  const whereOf = (name: string) => guide?.keys.find((key) => key.field === name)?.where
  const guideRef = useRef<HTMLDivElement>(null)

  const [mode, setMode] = useState<IntegrationMode>(initialMode)
  const [enabled, setEnabled] = useState(integration.enabled)
  const provider = integration.providers[mode]
  const fields = useMemo(() => provider?.config_fields ?? [], [provider])
  const [values, setValues] = useState<Record<string, ConfigValue>>(() => initialValues(fields, integration.config))
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  const [missing, setMissing] = useState<string[]>([])

  // The card's "Guía" button: bring the guide into view once the sheet has animated in (scrolling only the
  // sheet's body, so its header with the integration's name stays in place).
  useEffect(() => {
    if (!focusGuide) return
    const timer = window.setTimeout(() => {
      const guide = guideRef.current
      const body = guide?.closest<HTMLElement>('.overflow-y-auto')
      if (!guide || !body) return
      const top = body.scrollTop + guide.getBoundingClientRect().top - body.getBoundingClientRect().top - 12
      body.scrollTo({ top, behavior: 'smooth' })
    }, 250)
    return () => window.clearTimeout(timer)
  }, [focusGuide])

  const switchingToReal = mode === 'real' && integration.mode !== 'real'
  const dirty =
    mode !== integration.mode ||
    enabled !== integration.enabled ||
    Object.values(secrets).some(Boolean) ||
    removed.size > 0 ||
    fields.some((field) => !field.secret && (values[field.name] ?? null) !== (integration.config[field.name] ?? null))

  function changeMode(next: IntegrationMode) {
    setMode(next)
    setMissing([])
    const nextFields = integration.providers[next]?.config_fields ?? []
    setValues(initialValues(nextFields, integration.config))
  }

  function requiredMissing(): string[] {
    if (mode !== 'real') return []
    return fields
      .filter((field) => field.required)
      .filter((field) => {
        if (field.secret) {
          const configured = integration.secrets_configured[field.name] && !removed.has(field.name)
          return !configured && !secrets[field.name]
        }
        const value = values[field.name]
        const hasDefault = field.default !== null && field.default !== undefined && field.default !== ''
        return (value === null || value === undefined || value === '') && !hasDefault
      })
      .map((field) => field.name)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const lacking = requiredMissing()
    setMissing(lacking)
    if (lacking.length) return
    const body: IntegrationUpdate = {}
    if (mode !== integration.mode) body.mode = mode
    if (enabled !== integration.enabled) body.enabled = enabled
    if (fields.length) {
      const config: Record<string, ConfigValue> = {}
      for (const field of fields) {
        if (field.secret) continue
        const value = values[field.name] ?? null
        if (value !== (integration.config[field.name] ?? null)) config[field.name] = value
      }
      if (Object.keys(config).length) body.config = config
      const secretBody: Record<string, string | null> = {}
      for (const field of fields) {
        if (!field.secret) continue
        if (removed.has(field.name)) secretBody[field.name] = null
        else if (secrets[field.name]) secretBody[field.name] = secrets[field.name]
      }
      if (Object.keys(secretBody).length) body.secrets = secretBody
    }
    try {
      await update.mutateAsync({ kind: integration.kind, body })
      toast.success(t('integrations.toasts.saved', { name: title }))
      onClose()
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

  const fieldLabel = (name: string) => {
    const field = fields.find((item) => item.name === name)
    return field ? (lang === 'en' ? field.label_en : field.label_es) : name
  }
  // The provider's environment as the form stands (a select without a value uses its default: sandbox/staging).
  const environmentValue = values.environment ?? fields.find((field) => field.name === 'environment')?.default ?? null
  const environment = typeof environmentValue === 'string' ? environmentValue : null

  return (
    <form onSubmit={submit} className="flex h-full min-h-0 flex-col">
      <SheetHeader>
        <div className="flex items-center gap-3">
          <IntegrationIcon kind={integration.kind} real={integration.mode === 'real'} />
          <div className="min-w-0">
            <SheetTitle>{title}</SheetTitle>
            <SheetDescription>{kindText('description')}</SheetDescription>
          </div>
        </div>
      </SheetHeader>

      <SheetBody className="grid grid-cols-1 content-start gap-6">
        <fieldset className="grid gap-2">
          <legend className="eyebrow mb-2">{t('integrations.sheet.modeTitle')}</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {(['real', 'simulated'] as const).map((option) => {
              const available = modes.includes(option)
              const info = integration.providers[option]
              const Icon = option === 'real' ? Zap : FlaskConical
              const selected = mode === option
              return (
                <label
                  key={option}
                  className={cn(
                    'relative grid cursor-pointer content-start gap-1 rounded-lg border p-3 transition-colors',
                    'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/55',
                    selected ? 'border-accent bg-accent-soft/60' : 'border-border bg-surface hover:border-border-strong',
                    !available && 'cursor-not-allowed opacity-50',
                  )}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={option}
                    checked={selected}
                    disabled={!available}
                    onChange={() => changeMode(option)}
                    className="sr-only"
                  />
                  <span className="flex items-center gap-2 text-sm font-bold text-fg">
                    <Icon aria-hidden className={cn('size-4', selected ? 'text-accent-ink' : 'text-muted')} />
                    {t(`integrations.mode.${option}`)}
                  </span>
                  <span className="text-xs text-muted">
                    {available
                      ? lang === 'en' && info?.label_en
                        ? info.label_en
                        : info?.label
                      : integration.providers[option]
                        ? t('integrations.mode.offHere')
                        : t('integrations.mode.unavailable')}
                  </span>
                  <span className="text-xs text-fg/80">{kindText(option)}</span>
                </label>
              )
            })}
          </div>
        </fieldset>

        {mode === 'real' ? (
          <section className="grid grid-cols-1 gap-4">
            <p className="flex gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t('integrations.sheet.realWarning')}
            </p>
            <div ref={guideRef} className="min-w-0">
              <IntegrationGuide
                integration={integration}
                environment={environment}
                fieldLabel={fieldLabel}
                // open while it is not live yet (or when asked from the card); once live it folds away
                defaultOpen={focusGuide || !isLive(integration)}
              />
            </div>
            <div className="grid gap-4">
              <h3 className="eyebrow">{t('integrations.sheet.fieldsTitle')}</h3>
              {fields.length === 0 && <p className="text-sm text-muted">{t('integrations.sheet.noFields')}</p>}
              {fields.map((field) => (
                <ConfigFieldInput
                  key={field.name}
                  field={field}
                  value={values[field.name] ?? null}
                  onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))}
                  secretValue={secrets[field.name] ?? ''}
                  onSecretChange={(value) => setSecrets((current) => ({ ...current, [field.name]: value }))}
                  secretConfigured={integration.secrets_configured[field.name] ?? false}
                  secretRemoved={removed.has(field.name)}
                  onToggleRemove={() =>
                    setRemoved((current) => {
                      const next = new Set(current)
                      if (next.has(field.name)) next.delete(field.name)
                      else next.add(field.name)
                      return next
                    })
                  }
                  missing={missing.includes(field.name)}
                  where={whereOf(field.name)}
                />
              ))}
              {fields.some((field) => field.secret) && <p className="text-xs text-subtle">{t('integrations.sheet.secretHint')}</p>}
            </div>
          </section>
        ) : (
          <p className="text-sm text-muted">{t('integrations.sheet.simulatedNote')}</p>
        )}

        {missing.length > 0 && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {t('integrations.sheet.missingRequired', { fields: missing.map(fieldLabel).join(', ') })}
          </p>
        )}

        <div className="flex items-start justify-between gap-4 border-t border-border pt-5">
          <div className="min-w-0">
            <Label htmlFor={`${integration.kind}-enabled`}>{t('integrations.sheet.enabledLabel')}</Label>
            <p className="text-xs text-muted">{t('integrations.sheet.enabledHint')}</p>
          </div>
          <Switch id={`${integration.kind}-enabled`} name="enabled" checked={enabled} onCheckedChange={setEnabled} />
        </div>

        <section className="grid gap-2 rounded-lg border border-border bg-surface-2/60 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="eyebrow">{t('integrations.sheet.lastTest')}</h3>
            <IntegrationStatusPill integration={integration} />
          </div>
          <p className="text-[13px] break-words text-muted">
            {integration.last_checked_at
              ? `${formatRelative(integration.last_checked_at, lang)}${integration.status_message ? ` · ${integration.status_message}` : ''}`
              : t('integrations.sheet.neverTested')}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Button type="button" size="sm" onClick={() => void runTest()} loading={test.isPending} disabled={dirty}>
              {!test.isPending && <PlugZap aria-hidden />}
              {test.isPending ? t('integrations.card.testing') : t('integrations.card.test')}
            </Button>
            <span className="text-xs text-subtle">{dirty ? t('integrations.sheet.saveBeforeTest') : t('integrations.sheet.testUsesSaved')}</span>
          </div>
        </section>

        {meta.related && can(meta.related.permission) && (
          <Link
            to={meta.related.path}
            className="inline-flex w-fit items-center gap-1 rounded-sm text-[13px] font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {t(`integrations.related.${meta.related.key}`)}
            <ArrowUpRight aria-hidden className="size-3.5" />
          </Link>
        )}
      </SheetBody>

      <SheetFooter>
        <Button type="button" variant="secondary" onClick={onClose} disabled={update.isPending}>
          {t('actions.cancel', { ns: 'common' })}
        </Button>
        <Button type="submit" variant="primary" loading={update.isPending} disabled={!dirty}>
          {switchingToReal ? t('integrations.sheet.saveReal') : t('integrations.sheet.save')}
        </Button>
      </SheetFooter>
    </form>
  )
}
