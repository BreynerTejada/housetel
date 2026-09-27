import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { I18nText } from '../api'

/** Spanish and English versions of one text, side by side (stacked on phones). */
export function I18nTextInput({
  value,
  onChange,
  label,
  multiline = false,
  labelledBy,
  name,
  invalid,
  className,
  placeholder,
}: {
  value: I18nText
  onChange: (value: I18nText) => void
  /** Field name for the accessible label of each language input, e.g. "Nombre (en español)". */
  label?: string
  multiline?: boolean
  labelledBy?: string
  name?: string
  invalid?: boolean
  className?: string
  placeholder?: I18nText
}) {
  const { t } = useTranslation('inventory')
  const Control = multiline ? Textarea : Input
  return (
    <div className={cn('grid gap-2 sm:grid-cols-2', className)}>
      {(['es', 'en'] as const).map((lang) => (
        <label key={lang} className="grid gap-1">
          <span className="eyebrow !text-[10px]">{lang === 'es' ? t('common.inES') : t('common.inEN')}</span>
          <Control
            name={name ? `${name}.${lang}` : undefined}
            value={value?.[lang] ?? ''}
            placeholder={placeholder?.[lang]}
            aria-label={label ? t(lang === 'es' ? 'common.fieldInSpanish' : 'common.fieldInEnglish', { field: label }) : undefined}
            aria-describedby={labelledBy}
            aria-invalid={invalid || undefined}
            rows={multiline ? 3 : undefined}
            onChange={(event) => onChange({ ...value, [lang]: event.target.value })}
          />
        </label>
      ))}
    </div>
  )
}
