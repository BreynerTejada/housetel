import { KeyRound, MapPin } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ConfigField, ConfigValue } from '../api'

interface Props {
  field: ConfigField
  /** Non-secret value (config). */
  value: ConfigValue
  onChange: (value: ConfigValue) => void
  /** Secret fields: typed value (empty = keep what is stored). */
  secretValue?: string
  onSecretChange?: (value: string) => void
  secretConfigured?: boolean
  secretRemoved?: boolean
  onToggleRemove?: () => void
  missing?: boolean
  /** Where this value lives in the provider's panel (from the integration guide), shown under the input. */
  where?: string
}

/** One input generated from a provider's CONFIG_FIELDS entry (secrets are write-only password inputs). */
export function ConfigFieldInput({
  field,
  value,
  onChange,
  secretValue = '',
  onSecretChange,
  secretConfigured = false,
  secretRemoved = false,
  onToggleRemove,
  missing = false,
  where,
}: Props) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const id = useId()
  const helpId = `${id}-help`
  const whereId = `${id}-where`
  const label = lang === 'en' ? field.label_en : field.label_es
  const help = lang === 'en' ? field.help_en : field.help_es
  const hasDefault = field.default !== null && field.default !== undefined && field.default !== ''
  const showHelp = Boolean(help || (hasDefault && field.type !== 'select'))
  const describedBy = [showHelp ? helpId : null, where ? whereId : null].filter(Boolean).join(' ') || undefined

  if (field.type === 'boolean') {
    return (
      <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface-2/60 px-3 py-2.5">
        <div className="min-w-0">
          <Label htmlFor={id}>{label}</Label>
          {help && (
            <p id={helpId} className="text-xs text-muted">
              {help}
            </p>
          )}
        </div>
        <Switch
          id={id}
          name={field.name}
          checked={value === null || value === undefined ? Boolean(field.default) : Boolean(value)}
          onCheckedChange={(checked) => onChange(checked)}
          aria-describedby={help ? helpId : undefined}
        />
      </div>
    )
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id} className="flex items-center gap-1.5">
          {field.secret && <KeyRound aria-hidden className="size-3.5 text-subtle" />}
          {label}
          {field.required && <span className="text-danger-ink" aria-hidden>*</span>}
          {field.required && <span className="sr-only">({t('integrations.sheet.required')})</span>}
        </Label>
        {field.secret && secretConfigured && onToggleRemove && (
          <button
            type="button"
            onClick={onToggleRemove}
            className="rounded-sm text-xs font-semibold text-muted hover:text-danger-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {secretRemoved ? t('integrations.sheet.secretKeep') : t('integrations.sheet.secretRemove')}
          </button>
        )}
      </div>

      {field.secret ? (
        <Input
          id={id}
          name={field.name}
          type="password"
          autoComplete="new-password"
          spellCheck={false}
          value={secretValue}
          disabled={secretRemoved}
          onChange={(event) => onSecretChange?.(event.target.value)}
          placeholder={
            secretRemoved
              ? t('integrations.sheet.secretWillRemove')
              : secretConfigured
                ? t('integrations.sheet.secretConfigured')
                : t('integrations.sheet.secretEmpty')
          }
          aria-invalid={missing || undefined}
          aria-describedby={describedBy}
          className={cn(secretConfigured && !secretValue && !secretRemoved && 'placeholder:text-success-ink')}
        />
      ) : field.type === 'select' ? (
        <Select
          name={field.name}
          value={value === null || value === undefined ? (hasDefault ? String(field.default) : '') : String(value)}
          onValueChange={(next) => onChange(next)}
        >
          <SelectTrigger id={id} aria-invalid={missing || undefined} aria-describedby={describedBy}>
            <SelectValue placeholder={t('integrations.sheet.selectPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            {field.options.map((option) => (
              <SelectItem key={String(option.value)} value={String(option.value)}>
                {lang === 'en' ? option.label_en : option.label_es}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : field.type === 'textarea' ? (
        <Textarea
          id={id}
          name={field.name}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={missing || undefined}
          aria-describedby={describedBy}
        />
      ) : (
        <Input
          id={id}
          name={field.name}
          type={field.type === 'number' ? 'number' : field.type === 'url' ? 'url' : field.type === 'email' ? 'email' : 'text'}
          inputMode={field.type === 'number' ? 'numeric' : undefined}
          spellCheck={false}
          value={value === null || value === undefined ? '' : String(value)}
          placeholder={hasDefault ? String(field.default) : undefined}
          onChange={(event) => onChange(event.target.value === '' ? null : event.target.value)}
          aria-invalid={missing || undefined}
          aria-describedby={describedBy}
          className={field.type === 'number' ? 'num' : undefined}
        />
      )}

      {showHelp && (
        <p id={helpId} className="text-xs break-words text-muted">
          {help}
          {hasDefault && field.type !== 'select' && !help && t('integrations.sheet.default', { value: String(field.default) })}
        </p>
      )}
      {where && (
        <p id={whereId} className="flex items-start gap-1.5 text-xs break-words text-muted">
          <MapPin aria-hidden className="mt-px size-3.5 shrink-0 text-accent-ink" />
          <span>
            <span className="font-semibold text-fg/85">{t('integrations.guide.where')}</span> {where}
          </span>
        </p>
      )}
    </div>
  )
}
