import { useMutation } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { api, isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import {
  CUSTOM_FIELD_TARGETS,
  CUSTOM_FIELD_TYPES,
  useInvalidateInventory,
  type CustomFieldDefinition,
  type CustomFieldTarget,
  type CustomFieldType,
  type CustomValue,
  type I18nText,
} from '../api'
import { keyFromLabel } from '../lib/customValues'
import { CustomFieldInput } from './CustomFieldInput'
import { I18nTextInput } from './I18nTextInput'

const KEY_PATTERN = /^[a-z][a-z0-9_]{0,49}$/

interface OptionRow {
  value: string
  label: I18nText
  /** The stored value (maybe a number): sent back while the text is unchanged, so its uses stay valid. */
  original?: string | number
}

/** Create or edit a hotel-defined field. Target, key, type and scope are fixed once created. */
export function CustomFieldDialog({
  definition,
  defaultTarget = 'room_type',
  open,
  onOpenChange,
}: {
  definition?: CustomFieldDefinition
  defaultTarget?: CustomFieldTarget
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation('inventory')
  const invalidate = useInvalidateInventory()
  const editing = Boolean(definition)
  const [target, setTarget] = useState<CustomFieldTarget>(definition?.applies_to ?? defaultTarget)
  const [label, setLabel] = useState<I18nText>(definition?.label ?? {})
  const [key, setKey] = useState(definition?.key ?? '')
  const [keyTouched, setKeyTouched] = useState(editing)
  const [labelTouched, setLabelTouched] = useState(false)
  const [fieldType, setFieldType] = useState<CustomFieldType>(definition?.field_type ?? 'text')
  const [options, setOptions] = useState<OptionRow[]>(
    (definition?.options ?? []).map((option) => ({ value: String(option.value), label: option.label ?? {}, original: option.value })),
  )
  const [required, setRequired] = useState(definition?.required ?? false)
  const [defaultValue, setDefaultValue] = useState<CustomValue>(definition?.default_value ?? null)
  const [marketplace, setMarketplace] = useState(definition?.show_in_marketplace ?? false)
  const [scope, setScope] = useState<'organization' | 'property'>(definition?.scope ?? 'organization')
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const ids = { target: useId(), key: useId(), type: useId(), scope: useId() }
  const hasOptions = fieldType === 'select' || fieldType === 'multiselect'

  const cleanOptions = useMemo(
    () =>
      options
        .filter((option) => option.value.trim())
        .map((option) => ({
          value: option.original !== undefined && String(option.original) === option.value.trim() ? option.original : option.value.trim(),
          label: option.label.es?.trim() || option.label.en?.trim() ? option.label : { es: option.value.trim() },
        })),
    [options],
  )

  const errors: Record<string, string> = {}
  if (!label.es?.trim() && !label.en?.trim()) errors.label = t('common:validation.required')
  if (!KEY_PATTERN.test(key)) errors.key = t('customFields.keyRule')
  if (hasOptions && cleanOptions.length === 0) errors.options = t('customFields.needOptions')
  const values = cleanOptions.map((option) => option.value)
  if (new Set(values).size !== values.length) errors.options = t('customFields.repeatedOptions')
  const valid = Object.keys(errors).length === 0

  function updateLabel(next: I18nText) {
    setLabel(next)
    setLabelTouched(true)
    if (!keyTouched) setKey(keyFromLabel(next.es || next.en || ''))
  }

  const save = useMutation({
    mutationFn: () => {
      const body = {
        applies_to: target,
        key,
        label,
        field_type: fieldType,
        options: hasOptions ? cleanOptions : [],
        required,
        default_value: defaultValue === '' ? null : defaultValue,
        show_in_marketplace: marketplace,
        scope,
      }
      return definition
        ? api.patch<CustomFieldDefinition>(`/inventory/custom-fields/${definition.id}/`, {
            label: body.label,
            options: body.options,
            required: body.required,
            default_value: body.default_value,
            show_in_marketplace: body.show_in_marketplace,
          })
        : api.post<CustomFieldDefinition>('/inventory/custom-fields/', body)
    },
    onSuccess: () => {
      toast.success(editing ? t('customFields.saved') : t('customFields.created'))
      void invalidate()
      onOpenChange(false)
    },
    onError: (error) => {
      if (isApiError(error) && error.fields) {
        setServerErrors(Object.fromEntries(Object.entries(error.fields).map(([field, messages]) => [field, [messages].flat().join(' ')])))
      } else toast.error(errorMessage(error, t))
    },
  })

  const errorOf = (field: string) => serverErrors[field] ?? errors[field]
  const probe: CustomFieldDefinition = {
    id: 'probe',
    applies_to: target,
    key,
    label,
    field_type: fieldType,
    options: cleanOptions,
    required,
    default_value: null,
    show_in_marketplace: marketplace,
    sort_order: 0,
    scope,
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) save.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>{editing ? t('customFields.editTitle') : t('customFields.newTitle')}</DialogTitle>
            <DialogDescription>{t('customFields.dialogDescription')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <span id={ids.target} className="text-[13px] font-semibold">
                {t('customFields.appliesTo')}
              </span>
              <Select name="applies_to" value={target} onValueChange={(value) => setTarget(value as CustomFieldTarget)} disabled={editing}>
                <SelectTrigger aria-labelledby={ids.target}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CUSTOM_FIELD_TARGETS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`targets.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <span id={ids.type} className="text-[13px] font-semibold">
                {t('customFields.type')}
              </span>
              <Select name="field_type" value={fieldType} onValueChange={(value) => setFieldType(value as CustomFieldType)} disabled={editing}>
                <SelectTrigger aria-labelledby={ids.type}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CUSTOM_FIELD_TYPES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`fieldTypes.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-1.5" role="group" aria-label={t('fields.name')}>
            <span className="text-[13px] font-semibold">{t('fields.name')}</span>
            <I18nTextInput label={t('fields.name')} name="label" value={label} invalid={labelTouched && Boolean(errorOf('label'))} onChange={updateLabel} />
            {(serverErrors.label || (labelTouched && errors.label)) && (
              <p className="text-xs font-medium text-danger-ink">{serverErrors.label ?? errors.label}</p>
            )}
          </div>

          <div className="grid gap-1.5 sm:max-w-sm">
            <label htmlFor={ids.key} className="text-[13px] font-semibold">
              {t('customFields.key')}
            </label>
            <Input
              id={ids.key}
              name="key"
              className="num"
              value={key}
              disabled={editing}
              aria-invalid={Boolean(key && errorOf('key'))}
              aria-describedby={`${ids.key}-hint`}
              onChange={(event) => {
                setKey(event.target.value)
                setKeyTouched(true)
              }}
            />
            <span id={`${ids.key}-hint`} className={key && errorOf('key') ? 'text-xs font-medium text-danger-ink' : 'text-xs text-muted'}>
              {key && errorOf('key') ? errorOf('key') : t('customFields.keyHint')}
            </span>
          </div>

          {hasOptions && (
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-[13px] font-semibold">{t('customFields.options')}</legend>
              {options.map((option, index) => (
                <div key={index} className="grid items-start gap-2 sm:grid-cols-[9rem_minmax(0,1fr)_auto]">
                  <Input
                    name={`options.${index}.value`}
                    aria-label={t('customFields.optionValue', { index: index + 1 })}
                    placeholder={t('customFields.optionValuePlaceholder')}
                    value={option.value}
                    onChange={(event) => setOptions(options.map((row, i) => (i === index ? { ...row, value: event.target.value } : row)))}
                  />
                  <I18nTextInput
                    label={t('customFields.optionLabel', { index: index + 1 })}
                    name={`options.${index}.label`}
                    value={option.label}
                    onChange={(next) => setOptions(options.map((row, i) => (i === index ? { ...row, label: next } : row)))}
                  />
                  <Button variant="ghost" size="icon-sm" className="sm:mt-5" aria-label={t('customFields.removeOption', { index: index + 1 })}
                          onClick={() => setOptions(options.filter((_, i) => i !== index))}>
                    <X aria-hidden />
                  </Button>
                </div>
              ))}
              <Button variant="subtle" size="sm" className="w-fit" onClick={() => setOptions([...options, { value: '', label: {} }])}>
                <Plus aria-hidden />
                {t('customFields.addOption')}
              </Button>
              {errorOf('options') && <p className="text-xs font-medium text-danger-ink">{errorOf('options')}</p>}
            </fieldset>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-3">
              <Switch name="required" checked={required} onCheckedChange={setRequired} />
              <span className="grid">
                <span className="text-[13px] font-semibold">{t('customFields.required')}</span>
                <span className="text-xs text-muted">{t('customFields.requiredHint')}</span>
              </span>
            </label>
            {(target === 'room_type' || target === 'room') && (
              <label className="flex items-center gap-3">
                <Switch name="show_in_marketplace" checked={marketplace} onCheckedChange={setMarketplace} />
                <span className="grid">
                  <span className="text-[13px] font-semibold">{t('customFields.marketplace')}</span>
                  <span className="text-xs text-muted">{t('customFields.marketplaceHint')}</span>
                </span>
              </label>
            )}
          </div>

          {(!hasOptions || cleanOptions.length > 0) && (
            <div className="grid gap-1.5" role="group" aria-label={t('customFields.default')}>
              <span className="text-[13px] font-semibold">{t('customFields.default')}</span>
              <CustomFieldInput definition={probe} value={defaultValue ?? undefined} onChange={setDefaultValue} />
              {errorOf('default_value') && <p className="text-xs font-medium text-danger-ink">{errorOf('default_value')}</p>}
            </div>
          )}

          <div className="grid gap-1.5">
            <span id={ids.scope} className="text-[13px] font-semibold">
              {t('customFields.scope')}
            </span>
            <RadioGroup value={scope} onValueChange={(value) => setScope(value as 'organization' | 'property')} disabled={editing}
                        aria-labelledby={ids.scope} className="flex flex-wrap gap-4">
              {(['organization', 'property'] as const).map((item) => (
                <label key={item} className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value={item} />
                  {t(`customFields.scopes.${item}`)}
                </label>
              ))}
            </RadioGroup>
          </div>

          {errorOf('key') && serverErrors.key && <p className="text-sm font-medium text-danger-ink">{serverErrors.key}</p>}

          <DialogFooter>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!valid} loading={save.isPending}>
              {editing ? t('customFields.save') : t('customFields.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
