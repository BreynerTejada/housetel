import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ImagePlus, Search, Trash2 } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  deleteEngineImage,
  marketplaceKeys,
  patchEngineSettings,
  uploadEngineImage,
  type EngineSettings,
  type EngineSettingsInput,
  type I18nText,
} from '../../api'
import { brandStyle, contrastRatio, isHexColor, readableTextOn } from '../../lib/brand'
import { tr } from '../../lib/text'
import { HotelMark } from '../EngineShell'
import { SaveBar, SettingsSection } from './SettingsBits'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
/** WCAG AA for UI elements: the brand color draws borders, selected days and links on light surfaces. */
const MIN_UI_CONTRAST = 3
const WHITE = '#FFFFFF'

/** How readable the brand is: text on the color (buttons) when it works on light surfaces, else the problem. */
function brandContrast(color: string): { good: boolean; ratio: number } {
  const onLight = contrastRatio(color, WHITE)
  if (onLight < MIN_UI_CONTRAST) return { good: false, ratio: onLight }
  return { good: true, ratio: contrastRatio(color, readableTextOn(color)) }
}

function ratioText(ratio: number, lang: string): string {
  return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(ratio)
}

type Draft = Required<EngineSettingsInput>

function draftOf(settings: EngineSettings): Draft {
  return {
    enabled: settings.enabled,
    primary_color: settings.primary_color,
    headline: settings.headline ?? {},
    show_promo_field: settings.show_promo_field,
    allowed_rate_plans: settings.allowed_rate_plans,
    min_advance_hours: settings.min_advance_hours,
    max_advance_days: settings.max_advance_days,
    terms: settings.terms ?? {},
  }
}

/** Only the fields that changed (the API takes partial updates). */
function changes(draft: Draft, settings: EngineSettings): EngineSettingsInput {
  const original = draftOf(settings)
  const diff: Record<string, unknown> = {}
  for (const key of Object.keys(draft) as (keyof Draft)[]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(original[key])) diff[key] = draft[key]
  }
  return diff as EngineSettingsInput
}

function I18nFields({
  label,
  hint,
  value,
  onChange,
  multiline = false,
  maxLength,
}: {
  label: string
  hint: string
  value: I18nText
  onChange: (value: I18nText) => void
  multiline?: boolean
  maxLength: number
}) {
  const { t } = useTranslation('marketplace')
  const id = useId()
  const Field = multiline ? Textarea : Input
  return (
    <fieldset className="grid gap-2">
      <legend className="text-[13px] font-semibold text-fg">{label}</legend>
      <p className="-mt-1 text-xs text-muted">{hint}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {(['es', 'en'] as const).map((lang) => (
          <div key={lang} className="grid gap-1">
            <Label htmlFor={`${id}-${lang}`} className="text-xs font-medium text-muted">
              {lang === 'es' ? t('settings.engine.spanish') : t('settings.engine.english')}
            </Label>
            <Field
              id={`${id}-${lang}`}
              value={value[lang] ?? ''}
              maxLength={maxLength}
              rows={multiline ? 4 : undefined}
              onChange={(event) => onChange({ ...value, [lang]: event.target.value })}
            />
          </div>
        ))}
      </div>
    </fieldset>
  )
}

function ImageField({
  label,
  hint,
  kind,
  current,
  onUploaded,
}: {
  label: string
  hint: string
  kind: 'logo' | 'hero'
  current: string | null
  onUploaded: (settings: EngineSettings) => void
}) {
  const { t } = useTranslation('marketplace')
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: (file: File) => uploadEngineImage(kind, file),
    onSuccess: (settings) => {
      onUploaded(settings)
      toast.success(t('settings.engine.uploaded'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })
  const remove = useMutation({
    mutationFn: () => deleteEngineImage(kind),
    onSuccess: (settings) => {
      onUploaded(settings)
      toast.success(t('settings.engine.removed'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  function choose(file: File | undefined) {
    if (!file) return
    if (!IMAGE_TYPES.includes(file.type) || file.size > MAX_IMAGE_BYTES) {
      toast.error(t('settings.engine.imageInvalid'))
      return
    }
    upload.mutate(file)
  }

  return (
    <div className="grid gap-2">
      <p className="text-[13px] font-semibold text-fg">{label}</p>
      <div className="flex flex-wrap items-center gap-3">
        <div className={cn('grid shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-surface-2', kind === 'logo' ? 'size-16' : 'h-16 w-28')}>
          {current ? (
            <img src={current} alt="" className={cn('size-full', kind === 'logo' ? 'object-contain p-1.5' : 'object-cover')} />
          ) : (
            <span className="text-[11px] text-subtle">{t('settings.engine.noImage')}</span>
          )}
        </div>
        <input ref={input} type="file" accept={IMAGE_TYPES.join(',')} className="sr-only" tabIndex={-1} aria-hidden onChange={(event) => choose(event.target.files?.[0])} />
        <Button size="sm" onClick={() => input.current?.click()} loading={upload.isPending}>
          <ImagePlus aria-hidden />
          {current ? t('settings.engine.replace') : t('settings.engine.upload')}
          <span className="sr-only">: {label}</span>
        </Button>
        {current && (
          <Button size="sm" variant="ghost" onClick={() => remove.mutate()} loading={remove.isPending}>
            <Trash2 aria-hidden />
            {t('settings.engine.remove')}
            <span className="sr-only">: {label}</span>
          </Button>
        )}
      </div>
      <p className="text-xs text-muted">{hint}</p>
    </div>
  )
}

/** A miniature of the hotel's page with the draft brand, to see the color before saving. */
function EnginePreview({ draft, settings }: { draft: Draft; settings: EngineSettings }) {
  const { t, i18n } = useTranslation('marketplace')
  const color = isHexColor(draft.primary_color) ? draft.primary_color : settings.primary_color
  const headline = tr(draft.headline, i18n.language)
  return (
    <figure aria-label={t('settings.engine.preview')} style={brandStyle(color)} className="overflow-hidden rounded-xl border border-border bg-bg shadow-sm">
      <figcaption className="border-b border-border bg-surface-2 px-3 py-1.5 text-[11px] font-semibold text-muted">{t('settings.engine.preview')}</figcaption>
      <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2.5">
        <HotelMark config={{ name: settings.property.name, logo: settings.logo }} className="size-7 text-[11px]" />
        <span className="truncate text-sm font-extrabold text-fg">{settings.property.name}</span>
      </div>
      <div className="relative h-28 bg-accent-soft">
        {settings.hero_image && <img src={settings.hero_image} alt="" className="size-full object-cover" />}
        {headline && (
          <p className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent px-3 pt-6 pb-2.5 text-sm leading-snug font-bold text-white">
            {headline}
          </p>
        )}
      </div>
      <div className="grid gap-2 p-3">
        <div className="grid grid-cols-2 gap-2">
          <span className="h-8 rounded-md border border-border bg-surface" />
          <span className="h-8 rounded-md border border-border bg-surface" />
        </div>
        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-accent text-[13px] font-semibold text-on-accent">
          <Search aria-hidden className="size-3.5" />
          {t('settings.engine.previewSearch')}
        </span>
        <span className="text-[11px] font-semibold text-accent-ink">{t('engine.bestRate')}</span>
      </div>
    </figure>
  )
}

/** Booking engine settings: status, brand (color, logo, main image), texts and booking rules. */
export function EngineSettingsForm({ settings }: { settings: EngineSettings }) {
  const { t, i18n } = useTranslation(['marketplace', 'common'])
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft>(() => draftOf(settings))
  const diff = changes(draft, settings)
  const dirty = Object.keys(diff).length > 0
  const colorValid = isHexColor(draft.primary_color)
  const contrast = colorValid ? brandContrast(draft.primary_color) : null

  const save = useMutation({
    mutationFn: () => patchEngineSettings(diff),
    onSuccess: (saved) => {
      queryClient.setQueryData(marketplaceKeys.engineSettings, saved)
      setDraft(draftOf(saved))
      toast.success(t('settings.saved'))
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))
  const imagesSaved = (saved: EngineSettings) => queryClient.setQueryData(marketplaceKeys.engineSettings, saved)

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_17rem]">
      <div className="min-w-0">
        <SettingsSection title={t('settings.engine.status')}>
          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="block text-sm font-semibold text-fg">{t('settings.engine.enabled')}</span>
              <span className="block text-xs text-muted">{t('settings.engine.enabledHint')}</span>
            </span>
            <Switch checked={draft.enabled} onCheckedChange={(value) => set('enabled', value)} aria-label={t('settings.engine.enabled')} />
          </label>
        </SettingsSection>

        <SettingsSection title={t('settings.engine.brand')} hint={t('settings.engine.colorHint')}>
          <div className="grid gap-1.5">
            <Label htmlFor="engine-color-code">{t('settings.engine.color')}</Label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                aria-label={t('settings.engine.colorPicker')}
                value={colorValid ? draft.primary_color.toLowerCase() : '#000000'}
                onChange={(event) => set('primary_color', event.target.value.toUpperCase())}
                className="h-9 w-12 cursor-pointer rounded-md border border-border bg-surface p-1"
              />
              <Input
                id="engine-color-code"
                aria-label={t('settings.engine.colorCode')}
                value={draft.primary_color}
                maxLength={7}
                onChange={(event) => set('primary_color', event.target.value.trim().toUpperCase())}
                aria-invalid={!colorValid}
                className="num w-32 uppercase"
              />
            </div>
            {!colorValid ? (
              <p className="text-xs font-medium text-danger-ink">{t('settings.engine.colorInvalid')}</p>
            ) : (
              contrast && (
                <p className={cn('text-xs font-medium', contrast.good ? 'text-success-ink' : 'text-warning-ink')}>
                  {t(contrast.good ? 'settings.engine.contrastGood' : 'settings.engine.contrastLow', { ratio: ratioText(contrast.ratio, lang) })}
                </p>
              )
            )}
          </div>
          <ImageField
            label={t('settings.engine.logo')}
            hint={t('settings.engine.logoHint')}
            kind="logo"
            current={settings.logo || null}
            onUploaded={imagesSaved}
          />
          <ImageField label={t('settings.engine.hero')} hint={t('settings.engine.heroHint')} kind="hero" current={settings.hero_image} onUploaded={imagesSaved} />
        </SettingsSection>

        <SettingsSection title={t('settings.engine.texts')}>
          <I18nFields
            label={t('settings.engine.headline')}
            hint={t('settings.engine.headlineHint')}
            value={draft.headline}
            onChange={(value) => set('headline', value)}
            maxLength={120}
          />
          <I18nFields
            label={t('settings.engine.terms')}
            hint={t('settings.engine.termsHint')}
            value={draft.terms}
            onChange={(value) => set('terms', value)}
            maxLength={2000}
            multiline
          />
        </SettingsSection>

        <SettingsSection title={t('settings.engine.booking')}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="engine-min-advance">{t('settings.engine.minAdvance')}</Label>
              <Input
                id="engine-min-advance"
                type="number"
                min={0}
                max={720}
                value={draft.min_advance_hours}
                onChange={(event) => set('min_advance_hours', Math.max(0, Math.min(720, Number(event.target.value) || 0)))}
                className="num w-32"
              />
              <p className="text-xs text-muted">{t('settings.engine.minAdvanceHint')}</p>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="engine-max-advance">{t('settings.engine.maxAdvance')}</Label>
              <Input
                id="engine-max-advance"
                type="number"
                min={1}
                max={730}
                value={draft.max_advance_days}
                onChange={(event) => set('max_advance_days', Math.max(1, Math.min(730, Number(event.target.value) || 1)))}
                className="num w-32"
              />
              <p className="text-xs text-muted">{t('settings.engine.maxAdvanceHint')}</p>
            </div>
          </div>
          <label className="flex items-center justify-between gap-4">
            <span className="text-sm font-semibold text-fg">{t('settings.engine.promo')}</span>
            <Switch checked={draft.show_promo_field} onCheckedChange={(value) => set('show_promo_field', value)} aria-label={t('settings.engine.promo')} />
          </label>
          <fieldset className="grid gap-2">
            <legend className="text-[13px] font-semibold text-fg">{t('settings.engine.plans')}</legend>
            <p className="-mt-1 text-xs text-muted">{t('settings.engine.plansHint')}</p>
            {settings.rate_plans.length === 0 ? (
              <p className="text-sm text-muted">{t('settings.engine.noPlans')}</p>
            ) : (
              <ul className="grid gap-2">
                {settings.rate_plans.map((plan) => (
                  <li key={plan.id}>
                    <label className="flex items-center gap-2.5 text-sm text-fg">
                      <Checkbox
                        checked={draft.allowed_rate_plans.includes(plan.id)}
                        onCheckedChange={(checked) =>
                          set(
                            'allowed_rate_plans',
                            checked === true ? [...draft.allowed_rate_plans, plan.id] : draft.allowed_rate_plans.filter((id) => id !== plan.id),
                          )
                        }
                      />
                      <span>
                        {tr(plan.name, lang)} <span className="num text-xs text-muted">{plan.code}</span>
                      </span>
                      {!plan.sells_on_engine && <span className="text-xs text-warning-ink">{t('settings.engine.planOtherChannels')}</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
        </SettingsSection>
        <SaveBar visible={dirty} saving={save.isPending} onSave={() => colorValid && save.mutate()} onDiscard={() => setDraft(draftOf(settings))} />
      </div>
      <div className="xl:sticky xl:top-20 xl:self-start">
        <EnginePreview draft={draft} settings={settings} />
      </div>
    </div>
  )
}
