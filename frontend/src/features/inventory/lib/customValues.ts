import type { TFunction } from 'i18next'
import type { CustomFieldDefinition, CustomValue } from '../api'
import { tr } from './text'

/** Human text of a stored custom value. */
export function customValueText(definition: CustomFieldDefinition, value: CustomValue | undefined, lang: string, t: TFunction): string {
  if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
    return t('inventory:customFields.noValue')
  }
  if (definition.field_type === 'boolean') return value ? t('inventory:common.yes') : t('inventory:common.no')
  const labelOf = (item: string | number) => {
    const option = definition.options.find((candidate) => String(candidate.value) === String(item))
    return option ? tr(option.label, lang) || String(item) : String(item)
  }
  if (Array.isArray(value)) return value.map(labelOf).join(', ')
  if (definition.field_type === 'select') return labelOf(value as string)
  return String(value)
}

const KEY_START = /^[a-z]/

/** "Tipo de vista" → "tipo_de_vista" (the backend key rules: lowercase, digits, underscores). */
export function keyFromLabel(label: string): string {
  const base = label
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  const key = KEY_START.test(base) ? base : base ? `f_${base}` : ''
  return key.slice(0, 50)
}
