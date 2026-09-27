import { useTranslation } from 'react-i18next'
import { DatePicker } from '@/components/DatePicker'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { CustomFieldDefinition, CustomValue } from '../api'
import { tr } from '../lib/text'

const EMPTY = '__empty__'

/** The input for one hotel-defined field, by its type. */
export function CustomFieldInput({
  definition,
  value,
  onChange,
  labelledBy,
  id,
}: {
  definition: CustomFieldDefinition
  value: CustomValue | undefined
  onChange: (value: CustomValue) => void
  labelledBy?: string
  id?: string
}) {
  const { t, i18n } = useTranslation('inventory')
  const name = `custom_values.${definition.key}`
  // Radix works with text; the API stores each option's own value (possibly a number)
  const optionValue = (text: string) => definition.options.find((option) => String(option.value) === text)?.value ?? text

  switch (definition.field_type) {
    case 'boolean':
      return (
        <Switch
          id={id}
          name={name}
          aria-labelledby={labelledBy}
          checked={value === true}
          onCheckedChange={(checked) => onChange(checked)}
        />
      )
    case 'number':
      return (
        <Input
          id={id}
          name={name}
          type="number"
          aria-labelledby={labelledBy}
          className="w-full sm:w-48"
          value={typeof value === 'number' ? String(value) : ''}
          onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
        />
      )
    case 'date':
      return (
        <DatePicker
          id={id}
          aria-label={tr(definition.label, i18n.language)}
          value={typeof value === 'string' ? value : null}
          onChange={(next) => onChange(next)}
          className="w-full sm:w-64"
        />
      )
    case 'select':
      return (
        <Select
          name={name}
          value={value === null || value === undefined ? EMPTY : String(value)}
          onValueChange={(next) => onChange(next === EMPTY ? null : optionValue(next))}
        >
          <SelectTrigger id={id} aria-labelledby={labelledBy} className="w-full sm:w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={EMPTY}>{t('customFields.noValue')}</SelectItem>
            {definition.options.map((option) => (
              <SelectItem key={String(option.value)} value={String(option.value)}>
                {tr(option.label, i18n.language) || String(option.value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    case 'multiselect': {
      const selected = Array.isArray(value) ? value : []
      return (
        <div role="group" aria-labelledby={labelledBy} className="flex flex-wrap gap-x-4 gap-y-2">
          {definition.options.map((option) => {
            const text = String(option.value)
            const checked = selected.some((item) => String(item) === text)
            return (
              <label key={text} className="inline-flex items-center gap-2 text-sm">
                <Checkbox
                  name={`${name}.${text}`}
                  checked={checked}
                  onCheckedChange={(next) =>
                    onChange(next === true ? [...selected, option.value] : selected.filter((item) => String(item) !== text))
                  }
                />
                {tr(option.label, i18n.language) || text}
              </label>
            )
          })}
        </div>
      )
    }
    default:
      return (
        <Input
          id={id}
          name={name}
          aria-labelledby={labelledBy}
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(event.target.value)}
        />
      )
  }
}
